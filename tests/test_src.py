"""
Unit tests for src/ modules.

Run with:  pytest tests/ -v
"""

import pytest
from datetime import datetime, timedelta, timezone

# ── test yelp_scraper parsing ─────────────────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.yelp_scraper import parse_date, parse_rating, validate_review


class TestParseDate:
    def test_absolute_date_full_month(self):
        date, approx = parse_date("December 15, 2024")
        assert date == "2024-12-15"
        assert approx is False

    def test_absolute_date_abbreviated_month(self):
        date, approx = parse_date("Mar 3, 2025")
        assert date == "2025-03-03"
        assert approx is False

    def test_relative_days_ago(self):
        date, approx = parse_date("3 days ago")
        expected = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        assert date == expected
        assert approx is True  # relative dates are marked approximate

    def test_relative_weeks_ago(self):
        date, approx = parse_date("2 weeks ago")
        expected = (datetime.now(timezone.utc) - timedelta(weeks=2)).strftime("%Y-%m-%d")
        assert date == expected
        assert approx is True

    def test_relative_months_ago(self):
        date, approx = parse_date("1 month ago")
        # Approximate — just check format is valid ISO date
        assert len(date) == 10
        assert approx is True

    def test_unknown_format_falls_back_to_today(self):
        date, approx = parse_date("yesterday or something")
        assert date == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert approx is True

    def test_empty_string_falls_back_to_today(self):
        date, approx = parse_date("")
        assert date == datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TestParseRating:
    def test_four_stars_aria_label(self):
        rating, confident = parse_rating("4.0 out of 5 stars rating")
        assert rating == 4
        assert confident is True

    def test_five_stars_aria_label(self):
        rating, confident = parse_rating("5.0 out of 5 stars rating")
        assert rating == 5
        assert confident is True

    def test_decimal_stars(self):
        rating, confident = parse_rating("3.5 out of 5 stars")
        assert rating == 3  # floored
        assert confident is True

    def test_star_emoji(self):
        rating, confident = parse_rating("★★★★☆")
        assert rating == 4
        assert confident is True

    def test_unknown_returns_default(self):
        rating, confident = parse_rating("some weird text")
        assert rating == 3  # default
        assert confident is False


class TestValidateReview:
    def test_valid_review_returns_empty_warnings(self):
        review = {
            "id": "review_123",
            "reviewer_name": "John Doe",
            "rating": 4,
            "text": "Great food!",
        }
        warnings = validate_review(review, index=0)
        assert warnings == []

    def test_missing_id_returns_warning(self):
        review = {
            "id": "",
            "reviewer_name": "Jane",
            "rating": 5,
            "text": "Amazing!",
        }
        warnings = validate_review(review, index=1)
        assert any("Missing review ID" in w for w in warnings)

    def test_anonymous_reviewer_returns_warning(self):
        review = {
            "id": "abc",
            "reviewer_name": "Anonymous",
            "rating": 3,
            "text": "Okay.",
        }
        warnings = validate_review(review, index=0)
        assert any("anonymous" in w.lower() for w in warnings)

    def test_out_of_range_rating_returns_warning(self):
        review = {
            "id": "xyz",
            "reviewer_name": "Bob",
            "rating": 0,   # invalid
            "text": "Bad.",
        }
        warnings = validate_review(review, index=0)
        assert any("Suspicious rating" in w for w in warnings)

    def test_no_text_returns_warning(self):
        review = {
            "id": "no_text_review",
            "reviewer_name": "Alice",
            "rating": 3,
            "text": "",
        }
        warnings = validate_review(review, index=0)
        assert any("No review text" in w for w in warnings)


# ── test state_store ───────────────────────────────────────────────────────────

import tempfile, os as _os
from src.state_store import StateStore


class TestStateStore:
    def test_mark_and_check(self, tmp_path):
        db = str(tmp_path / "test.db")
        store = StateStore(db)

        store.mark_processed("review_1", "replied", "Thanks!")
        assert store.has_processed("review_1") is True
        assert store.has_processed("review_2") is False

    def test_mark_batch(self, tmp_path):
        db = str(tmp_path / "batch.db")
        store = StateStore(db)

        records = [
            {"review_key": f"r{i}", "action": "replied", "reply_preview": f"Reply {i}"}
            for i in range(10)
        ]
        count = store.mark_batch(records)
        assert count == 10
        assert store.get_stats()["total"] == 10

    def test_stats(self, tmp_path):
        db = str(tmp_path / "stats.db")
        store = StateStore(db)

        store.mark_processed("r1", "replied", "a")
        store.mark_processed("r2", "dry_run_generated", "b")
        store.mark_processed("r3", "dry_run_generated", "c")
        store.mark_processed("r4", "skipped", "d")

        s = store.get_stats()
        assert s["total"] == 4
        assert s["replied"] == 1
        assert s["dry_run"] == 2
        assert s["skipped"] == 1

    def test_reset(self, tmp_path):
        db = str(tmp_path / "reset.db")
        store = StateStore(db)
        store.mark_processed("r1", "replied", "a")
        store.mark_processed("r2", "replied", "b")
        assert store.get_stats()["total"] == 2

        store.reset()
        assert store.get_stats()["total"] == 0
        assert store.has_processed("r1") is False

    def test_get_recent(self, tmp_path):
        db = str(tmp_path / "recent.db")
        store = StateStore(db)

        for i in range(5):
            store.mark_processed(f"r{i}", "replied", f"reply {i}")

        recent = store.get_recent(limit=3)
        assert len(recent) == 3  # limited to 3


# ── test workflow helpers ───────────────────────────────────────────────────────

from src.workflow import normalize_review_key, extract_review_id, _star_to_int


class TestWorkflowHelpers:
    def test_normalize_review_key_from_name(self):
        review = {"name": "accounts/123/locations/456/reviews/789"}
        assert normalize_review_key(review) == "accounts/123/locations/456/reviews/789"

    def test_normalize_review_key_from_id(self):
        review = {"reviewId": "review_abc"}
        assert normalize_review_key(review) == "review_abc"

    def test_normalize_review_key_fallback_hash(self):
        review = {"comment": "Great sushi!"}
        key = normalize_review_key(review)
        assert isinstance(key, str)
        assert len(key) > 0

    def test_extract_review_id_from_reviewId(self):
        review = {"reviewId": "xyz_123"}
        assert extract_review_id(review) == "xyz_123"

    def test_extract_review_id_from_name(self):
        review = {"name": "accounts/123/locations/456/reviews/789"}
        assert extract_review_id(review) == "789"

    def test_star_to_int(self):
        assert _star_to_int("FOUR") == 4
        assert _star_to_int("ONE") == 1
        assert _star_to_int(5) == 5
        assert _star_to_int(2) == 2
        assert _star_to_int("UNKNOWN") == 3  # default


if __name__ == "__main__":
    pytest.main([__file__, "-v"])