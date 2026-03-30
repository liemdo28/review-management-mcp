import json
import os
from datetime import datetime, timezone


class StateStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"processed_reviews": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"processed_reviews": {}}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def has_processed(self, review_key: str) -> bool:
        return review_key in self.data.get("processed_reviews", {})

    def mark_processed(
        self,
        review_key: str,
        action: str,
        reply_preview: str,
    ) -> None:
        self.data.setdefault("processed_reviews", {})[review_key] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "reply_preview": reply_preview[:300],
        }
        self.save()

    def get_stats(self) -> dict:
        reviews = self.data.get("processed_reviews", {})
        return {
            "total": len(reviews),
            "replied": sum(1 for r in reviews.values() if r.get("action") == "replied"),
            "dry_run": sum(1 for r in reviews.values() if r.get("action") == "dry_run_generated"),
        }