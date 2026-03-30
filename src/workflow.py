from typing import Any
from src.config import settings
from src.google_auth import get_google_access_token
from src.google_reviews import list_reviews, reply_to_review
from src.ai_reply import build_reply
from src.state_store import StateStore


def normalize_review_key(review: dict) -> str:
    return review.get("name") or review.get("reviewId") or str(hash(review.get("comment", "")))


def extract_review_id(review: dict) -> str:
    if review.get("reviewId"):
        return review["reviewId"]
    name = review.get("name", "")
    return name.split("/")[-1] if name else str(hash(name))


def should_reply(review: dict, state_store: StateStore) -> tuple[bool, str]:
    review_key = normalize_review_key(review)

    if state_store.has_processed(review_key):
        return False, "already_processed"

    if review.get("reviewReply"):
        return False, "already_has_reply"

    return True, "ok"


class WorkflowResult:
    def __init__(self):
        self.total_seen: int = 0
        self.total_replied: int = 0
        self.total_skipped: int = 0
        self.total_error: int = 0
        self.reviews: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def add_review(self, review_data: dict[str, Any]) -> None:
        self.reviews.append(review_data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_seen": self.total_seen,
            "total_replied": self.total_replied,
            "total_skipped": self.total_skipped,
            "total_error": self.total_error,
            "reviews": self.reviews,
            "errors": self.errors,
        }


def run(logger, dry_run: bool | None = None, on_progress=None) -> WorkflowResult:
    """
    Main workflow: fetch reviews, generate replies, optionally post.
    on_progress: callable(str) for UI updates
    """
    state_store = StateStore(settings.state_file)
    effective_dry_run = dry_run if dry_run is not None else settings.dry_run

    result = WorkflowResult()

    try:
        access_token = get_google_access_token(
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_refresh_token,
        )
    except Exception as e:
        logger.error(f"Failed to get access token: {e}")
        result.errors.append(f"Auth error: {e}")
        return result

    for location_id, location_name in settings.location_ids:
        if on_progress:
            on_progress(f"Checking {location_name}...")

        logger.info(f"Checking location: {location_name} ({location_id})")

        try:
            reviews = list_reviews(
                access_token=access_token,
                account_id=settings.google_account_id,
                location_id=location_id,
            )
            logger.info(f"Fetched {len(reviews)} reviews from {location_name}")
        except Exception as e:
            logger.error(f"Failed to fetch reviews from {location_name}: {e}")
            result.errors.append(f"Fetch error [{location_name}]: {e}")
            continue

        for review in reviews:
            result.total_seen += 1
            review_key = normalize_review_key(review)
            review_id = extract_review_id(review)

            ok, reason = should_reply(review, state_store)
            if not ok:
                result.total_skipped += 1
                logger.info(f"Skip review={review_id} reason={reason}")
                continue

            # Build reply
            try:
                reply_text = build_reply(
                    review=review,
                    restaurant_name="Raw Sushi Bistro" if "raw-sushi" in location_name.lower() else "Bakudan Ramen",
                    location=location_name,
                    api_key=settings.openai_api_key,
                    model=settings.openai_model,
                )
            except Exception as e:
                logger.error(f"Failed to generate reply for {review_id}: {e}")
                result.total_error += 1
                result.errors.append(f"AI error [{review_id}]: {e}")
                continue

            logger.info(f"Generated reply for {review_id}: {reply_text[:80]}...")

            # Add to result for UI display
            review_data = {
                "review_id": review_id,
                "location_name": location_name,
                "reviewer_name": (
                    review.get("reviewer", {}).get("displayName", "")
                    or review.get("reviewerName", "Guest")
                ),
                "rating": review.get("starRating", "UNKNOWN"),
                "text": review.get("comment", ""),
                "reply_text": reply_text,
                "action": "dry_run" if effective_dry_run else "pending",
            }
            result.add_review(review_data)

            if effective_dry_run:
                logger.info("DRY_RUN enabled. Not posting reply.")
                state_store.mark_processed(review_key, "dry_run_generated", reply_text)
            else:
                try:
                    reply_to_review(
                        access_token=access_token,
                        account_id=settings.google_account_id,
                        location_id=location_id,
                        review_id=review_id,
                        comment=reply_text,
                    )
                    logger.info(f"Posted reply to {review_id}")
                    state_store.mark_processed(review_key, "replied", reply_text)
                    result.total_replied += 1
                except Exception as e:
                    logger.error(f"Failed to post reply to {review_id}: {e}")
                    result.total_error += 1
                    result.errors.append(f"Post error [{review_id}]: {e}")

    logger.info(
        f"Done. seen={result.total_seen} replied={result.total_replied} "
        f"skipped={result.total_skipped} errors={result.total_error}"
    )
    return result