"""
StateStore v2 — SQLite-backed review tracking.

Replaces JSON file-based StateStore with SQLite for:
- Atomic transactions (no race conditions)
- Concurrent-safe writes
- Efficient queries at scale (500k+ reviews)
- Proper indexes for fast lookups

Migration: auto-creates tables on first run.
Old JSON state is NOT auto-migrated (reset on upgrade).
"""

import sqlite3
import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("review_bot")


class StateStore:
    """
    SQLite-backed state store for processed reviews.

    Usage:
        store = StateStore("state/reviews.db")
        store.mark_processed("review_123", "replied", "Thank you...")
        if store.has_processed("review_123"):
            print("Already processed")

    Table schema:
        processed_reviews (
            review_key   TEXT PRIMARY KEY,
            action       TEXT NOT NULL,   -- 'replied', 'dry_run_generated', 'skipped'
            reply_preview TEXT,
            processed_at TEXT NOT NULL,   -- ISO timestamp
            source       TEXT,            -- 'google', 'yelp'
            location_name TEXT,
            rating       INTEGER,
            reviewer_name TEXT
        )
    """

    def __init__(self, db_path: str = "state/reviews.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        """Create a new SQLite connection with WAL mode for concurrency."""
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level="IMMEDIATE")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def _transaction(self):
        """Context manager for atomic transactions."""
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_reviews (
                    review_key     TEXT PRIMARY KEY,
                    action         TEXT NOT NULL,
                    reply_preview  TEXT,
                    processed_at   TEXT NOT NULL,
                    source         TEXT,
                    location_name  TEXT,
                    rating         INTEGER,
                    reviewer_name  TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action
                ON processed_reviews(action)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_at
                ON processed_reviews(processed_at)
            """)
        logger.info(f"StateStore initialized: {self.db_path}")

    # ── Public API ──────────────────────────────────────────────────────────────

    def has_processed(self, review_key: str) -> bool:
        """Check if a review has been processed."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_reviews WHERE review_key = ?",
                (review_key,)
            )
            return cursor.fetchone() is not None

    def mark_processed(
        self,
        review_key: str,
        action: str,
        reply_preview: str = "",
        source: str = "",
        location_name: str = "",
        rating: int = 0,
        reviewer_name: str = "",
    ) -> None:
        """
        Record that a review has been processed.

        Uses INSERT OR REPLACE so concurrent writes are safe.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._transaction() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO processed_reviews
                    (review_key, action, reply_preview, processed_at,
                     source, location_name, rating, reviewer_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                review_key,
                action,
                reply_preview[:300] if reply_preview else "",
                timestamp,
                source,
                location_name,
                rating,
                reviewer_name,
            ))
        logger.debug(f"Marked processed: {review_key} [{action}]")

    def mark_batch(self, records: list[dict]) -> int:
        """
        Bulk insert multiple processed records in one transaction.

        Args:
            records: list of dicts with keys:
                review_key, action, reply_preview, source,
                location_name, rating, reviewer_name

        Returns:
            Number of records inserted/updated.
        """
        if not records:
            return 0

        timestamp = datetime.now(timezone.utc).isoformat()
        with self._transaction() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO processed_reviews
                    (review_key, action, reply_preview, processed_at,
                     source, location_name, rating, reviewer_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r.get("review_key", ""),
                    r.get("action", ""),
                    (r.get("reply_preview") or "")[:300],
                    timestamp,
                    r.get("source", ""),
                    r.get("location_name", ""),
                    r.get("rating", 0),
                    r.get("reviewer_name", ""),
                )
                for r in records
            ])
            return len(records)

    def get_stats(self) -> dict:
        """Return aggregated statistics."""
        with self._transaction() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews"
            ).fetchone()[0]

            replied = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews WHERE action = 'replied'"
            ).fetchone()[0]

            dry_run = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews WHERE action = 'dry_run_generated'"
            ).fetchone()[0]

            skipped = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews WHERE action = 'skipped'"
            ).fetchone()[0]

            google_count = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews WHERE source = 'google'"
            ).fetchone()[0]

            yelp_count = conn.execute(
                "SELECT COUNT(*) FROM processed_reviews WHERE source = 'yelp'"
            ).fetchone()[0]

        return {
            "total": total,
            "replied": replied,
            "dry_run": dry_run,
            "skipped": skipped,
            "google": google_count,
            "yelp": yelp_count,
        }

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Get most recent processed reviews."""
        with self._transaction() as conn:
            rows = conn.execute("""
                SELECT review_key, action, reply_preview, processed_at,
                       source, location_name, rating, reviewer_name
                FROM processed_reviews
                ORDER BY processed_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        return [
            {
                "review_key": r[0],
                "action": r[1],
                "reply_preview": r[2],
                "processed_at": r[3],
                "source": r[4],
                "location_name": r[5],
                "rating": r[6],
                "reviewer_name": r[7],
            }
            for r in rows
        ]

    def reset(self) -> None:
        """Clear all state (for testing/reset)."""
        with self._transaction() as conn:
            conn.execute("DELETE FROM processed_reviews")
        logger.warning("StateStore reset — all processed review records cleared.")

    def vacuum(self) -> None:
        """Optimize the database file."""
        with self._transaction() as conn:
            conn.execute("VACUUM")
        logger.info("StateStore vacuumed.")