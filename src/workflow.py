"""
Main workflow for Google Business Profile reviews.

Handles:
- Google OAuth token refresh
- Review fetching per location
- AI reply generation (via OpenAI)
- Reply posting (with DRY RUN mode)
- State tracking via SQLite (no duplicate replies)
- Progress callbacks for UI

Fixed:
- C-03: DRY RUN now increments total_generated counter
- Updated to use new StateStore SQLite API
- Added proper structured logging throughout
"""

import logging
from typing import Any, Optional

from src.config import settings
from src.google_auth import get_google_access_token, GoogleAuthError
from src.google_reviews import list_reviews, reply_to_review, GoogleReviewAPIError
from src.ai_reply import build_reply
from src.state_store import StateStore


logger = logging.getLogger("review_bot")

# ── Helpers ────────────────────────────────────────────────────────────────────

def normalize_review_key(review: dict) -> str:
    """Derive a stable key for deduplication."""
    return review.get("name") or review.get("reviewId") or str(hash(review.get("comment", "")))


def extract_review_id(review: dict) -> str:
    """Extract the review ID from a review dict."""
    if review.get("reviewId"):
        return review["reviewId"]
    name = review.get("name", "")
    return name.split("/")[-1] if name else str(hash(name))


def _get_restaurant_name(location_name: str) -> str:
    """Derive restaurant name from location label."""
    loc_lower = location_name.lower()
    if "raw sushi" in loc_lower:
        return "Raw Sushi Bistro"
    if "bakudan" in loc_lower:
        return "Bakudan Ramen"
    return "Restaurant"


def should_reply(review: dict, state_store: StateStore) -> tuple[bool, str]:
    """Check if a review should receive a reply."""
    review_key = normalize_review_key(review)

    if state_store.has_processed(review_key):
        return False, "already_processed"

    if review.get("reviewReply"):
        return False, "already_has_reply"

    return True, "ok"


# ── Result container ───────────────────────────────────────────────────────────

class WorkflowResult:
    """Aggregated result from a workflow run."""

    def __init__(self):
        self.total_seen: int = 0
        self.total_generated: int = 0  # FIX C-03: AI replies generated (DRY RUN or real)
        self.total_replied: int = 0   # Actually posted to Google
        self.total_skipped: int = 0
        self.total_error: int = 0
        self.reviews: list[dict] = []
        self.errors: list[str] = []

    def add_review(self, review_data: dict) -> None:
        self.reviews.append(review_data)

    def summary(self) -> dict:
        return {
            "seen": self.total_seen,
            "generated": self.total_generated,
            "replied": self.total_replied,
            "skipped": self.total_skipped,
            "errors": self.total_error,
        }


# ── Main workflow ───────────────────────────────────────────────────────────────

def run(
    logger: logging.Logger,
    dry_run: Optional[bool] = None,
    on_progress: Optional[callable] = None,
) -> WorkflowResult:
    """
    Run the full Google review → reply workflow.

    Args:
        logger: structured logger (from src/logger.py)
        dry_run: override DRY_RUN setting (None = use .env setting)
        on_progress: callable(str) called with progress messages (for UI)

    Returns:
        WorkflowResult with counts + review data for UI display
    """
    state_store = StateStore(settings.state_file)
    effective_dry_run = dry_run if dry_run is not None else settings.dry_run

    result = WorkflowResult()
    progress = on_progress or (lambda _: None)

    logger.info(f"Workflow starting (DRY_RUN={effective_dry_run})")

    # ── Auth ─────────────────────────────────────────────────────────────────
    try:
        access_token = get_google_access_token(
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_refresh_token,
        )
        progress("✅ Authenticated with Google")
    except GoogleAuthError as e:
        logger.error(f"Google auth failed: {e}")
        result.errors.append(f"Auth error: {e}")
        progress(f"❌ Auth failed: {e}")
        return result

    # ── Process each location ────────────────────────────────────────────────
    for location_id, location_name in settings.location_ids:
        progress(f"📍 Checking {location_name}...")

        try:
            reviews = list_reviews(
                access_token=access_token,
                account_id=settings.google_account_id,
                location_id=location_id,
            )
            logger.info(f"Fetched {len(reviews)} reviews from {location_name}")
            progress(f"  → {len(reviews)} reviews found")
        except GoogleReviewAPIError as e:
            logger.error(f"Failed to fetch reviews from {location_name}: {e}")
            result.errors.append(f"Fetch error [{location_name}]: {e}")
            progress(f"  ❌ Fetch failed: {e}")
            continue

        # ── Process each review ─────────────────────────────────────────────
        for review in reviews:
            result.total_seen += 1
            review_key = normalize_review_key(review)
            review_id = extract_review_id(review)

            ok, reason = should_reply(review, state_store)
            if not ok:
                result.total_skipped += 1
                logger.debug(f"Skip {review_id} [{reason}]")
                continue

            # ── AI Reply ────────────────────────────────────────────────────
            try:
                reply_text = build_reply(
                    review=review,
                    restaurant_name=_get_restaurant_name(location_name),
                    location=location_name,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
                result.total_generated += 1  # FIX C-03: always increment
                logger.info(f"Generated reply for {review_id}: {reply_text[:60]}...")
            except Exception as e:
                logger.error(f"AI reply failed for {review_id}: {e}")
                result.total_error += 1
                result.errors.append(f"AI error [{review_id}]: {e}")
                progress(f"  ⚠️ AI failed for {review_id}: {e}")
                continue

            # ── Compose review data for UI ───────────────────────────────────
            reviewer_name = (
                (review.get("reviewer", {}) or {}).get("displayName", "")
                or review.get("reviewerName", "Guest")
            )
            rating_raw = review.get("starRating", "UNKNOWN")

            review_data = {
                "review_id": review_id,
                "review_key": review_key,
                "location_name": location_name,
                "reviewer_name": reviewer_name,
                "rating": rating_raw,
                "text": review.get("comment", ""),
                "reply_text": reply_text,
                "action": "dry_run" if effective_dry_run else "pending",
                "source": "google",
            }
            result.add_review(review_data)

            # ── Post or simulate ─────────────────────────────────────────────
            if effective_dry_run:
                logger.info(f"[DRY RUN] Would post to {review_id}: {reply_text[:60]}...")
                state_store.mark_processed(
                    review_key=review_key,
                    action="dry_run_generated",
                    reply_preview=reply_text,
                    source="google",
                    location_name=location_name,
                    rating=_star_to_int(rating_raw),
                    reviewer_name=reviewer_name,
                )
                progress(f"  ✅ [DRY RUN] Generated reply for {reviewer_name} (⭐{_star_to_int(rating_raw)})")
            else:
                try:
                    reply_to_review(
                        access_token=access_token,
                        account_id=settings.google_account_id,
                        location_id=location_id,
                        review_id=review_id,
                        comment=reply_text,
                    )
                    result.total_replied += 1
                    logger.info(f"Posted reply to {review_id}")
                    state_store.mark_processed(
                        review_key=review_key,
                        action="replied",
                        reply_preview=reply_text,
                        source="google",
                        location_name=location_name,
                        rating=_star_to_int(rating_raw),
                        reviewer_name=reviewer_name,
                    )
                    progress(f"  ✅ Replied to {reviewer_name} (⭐{_star_to_int(rating_raw)})")
                except GoogleReviewAPIError as e:
                    logger.error(f"Post failed for {review_id}: {e}")
                    result.total_error += 1
                    result.errors.append(f"Post error [{review_id}]: {e}")
                    progress(f"  ❌ Post failed for {review_id}: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = result.summary()
    logger.info(
        f"Workflow done | "
        f"seen={summary['seen']} "
        f"generated={summary['generated']} "
        f"replied={summary['replied']} "
        f"skipped={summary['skipped']} "
        f"errors={summary['errors']}"
    )
    progress(f"✅ Done! {summary['generated']} generated, {summary['replied']} replied")

    return result


def _star_to_int(star: str | int) -> int:
    """Convert star rating string to int."""
    mapping = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
    if isinstance(star, int):
        return min(5, max(1, star))
    return mapping.get(str(star).upper(), 3)


def run_yelp_workflow(
    logger: logging.Logger,
    reviews: list[dict],
    location_key: str,
    location_name: str,
    on_progress: Optional[callable] = None,
) -> WorkflowResult:
    """
    Yelp-specific workflow: generate AI replies for scraped reviews.

    Differs from Google workflow:
    - No posting (Yelp doesn't support programmatic reply without Partner API)
    - Always saves to SQLite state
    - Can export to Google Sheets
    """
    state_store = StateStore(settings.state_file)
    result = WorkflowResult()
    progress = on_progress or (lambda _: None)

    logger.info(f"Yelp workflow starting ({len(reviews)} reviews)")

    for review in reviews:
        result.total_seen += 1
        review_key = review.get("review_key", "") or review.get("id", "") or str(hash(str(review)))

        # Skip duplicates
        if state_store.has_processed(review_key):
            result.total_skipped += 1
            continue

        # Generate AI reply
        try:
            reply_text = build_reply(
                review={
                    "starRating": _yelp_rating_to_star(review.get("rating", 3)),
                    "comment": review.get("text", ""),
                    "reviewer": {"displayName": review.get("reviewer_name", "Guest")},
                },
                restaurant_name=review.get("business_name", location_name),
                location=review.get("location_name", location_name),
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
            result.total_generated += 1
        except Exception as e:
            logger.error(f"AI failed for {review_key}: {e}")
            result.total_error += 1
            result.errors.append(f"AI error: {e}")
            continue

        # Store in state
        state_store.mark_processed(
            review_key=review_key,
            action="yelp_generated",
            reply_preview=reply_text,
            source="yelp",
            location_name=location_name,
            rating=review.get("rating", 0),
            reviewer_name=review.get("reviewer_name", "Guest"),
        )

        result.add_review({
            "review_id": review.get("id", ""),
            "review_key": review_key,
            "location_name": location_name,
            "reviewer_name": review.get("reviewer_name", "Guest"),
            "rating": _yelp_rating_to_star(review.get("rating", 3)),
            "text": review.get("text", ""),
            "reply_text": reply_text,
            "action": "yelp_generated",
            "source": "yelp",
        })

        progress(f"  ✅ {review.get('reviewer_name', 'Guest')} (⭐{review.get('rating', 0)})")

    logger.info(f"Yelp workflow done: generated={result.total_generated} skipped={result.total_skipped}")
    return result


def _yelp_rating_to_star(rating) -> str:
    """Convert numeric rating to Yelp star string."""
    stars = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE"}
    if isinstance(rating, int) and rating in stars:
        return stars[rating]
    return "THREE"