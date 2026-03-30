# Dev Handoff Review — Review Management Desktop App

**Status:** MVP / Prototype — not production-ready
**Reviewer:** QA Team
**Date:** 2026-03-30

---

## One-liner

> Good prototype, not production-ready.

---

## What Works (Keep These)

- Module separation (config, auth, reviews, AI, state, workflow)
- `tenacity` retry on Google API calls
- `StateStore` duplicate-prevention logic
- DRY RUN mode
- Dark-themed Tkinter UI (good UX direction)
- README + test checklist

---

## Critical — Fix Before Any Real Load

### 1. StateStore JSON → Race Condition + Corruption

**File:** `src/state_store.py`

Full file read/write on every `mark_processed()`. Multiple processes = data loss or corruption.

```
StateStore._load() → self.data = ... → save() [full overwrite]
```

**Fix:** Replace with SQLite. One transaction per `mark_processed`.

---

### 2. Google Sheets is NOT a data store

**File:** `src/google_sheets.py`

`save_reviews_to_sheet()` does `col_values(1)` (reads all rows) on every save. `update_review_reply_status` uses `find()` which scans every row. Both are O(n) and hit Google Sheets rate limits fast.

**Fix:** Use a database as primary store. Sheets = read-only export / reporting only.

---

### 3. DRY RUN counter bug

**File:** `src/workflow.py` → `run()`

When `DRY_RUN=true`, reviews are processed and AI replies generated, but `total_replied` is never incremented. UI shows "Replied: 0" after a successful dry run — misleading.

```python
if effective_dry_run:
    state_store.mark_processed(review_key, "dry_run_generated", reply_text)
    continue  # ← total_replied is NOT updated
```

**Fix:** Add `total_generated` counter for DRY RUN mode.

---

### 4. Yelp Selenium selectors are fragile

**File:** `src/yelp_scraper.py`

CSS selectors like `[data-review-id]`, `.review`, `[class*='user']` break the moment Yelp updates their HTML. `except: continue` silently swallows all failures — zero error signal.

**Fix:**
- Add schema validation per scraped review (raise if `id` or `text` is missing)
- Log every skip with reason
- Add `--dry-run --verbose` flag so testers can see what's happening

---

### 5. `_log_google()` is a no-op

**File:** `app.py`

```python
def _log_google(self, msg: str):
    pass  # ← Nothing happens
```

Google workflow progress is invisible to users. App appears frozen during API calls.

**Fix:** Wire `_log_google` to a ScrolledText widget in the Google tab. Add progress logging.

---

## High — Fix Before Beta / Internal Use

### 6. Yelp row selection is a stub

**File:** `app.py` → `on_yelp_select()`

Clicking a Yelp row does nothing — handler is incomplete. The tree shows data but there's no preview panel interaction.

**Fix:** Store full review objects in parallel with tree rows. Populate AI reply preview on click.

---

### 7. Google row selection is missing

**File:** `app.py` → `tree_google`

`tree_google` has no `<<TreeviewSelect>>` binding. No reply preview shows when a row is selected.

**Fix:** Bind selection event and populate `reply_text_google` from the selected review's data.

---

### 8. AI reply uses generic "Restaurant" + empty location

**File:** `app.py` → `scrape_yelp_to_sheets()`

```python
reply = generate_ai_reply(
    restaurant_name="Restaurant",  # ← Always "Restaurant"
    location="",                   # ← Always empty
    ...
)
```

**Fix:** Parse real business name from Yelp page. Use the URL dropdown lookup to get the correct name before generating.

---

### 9. Google Sheets auth: OAuth2 vs Service Account confusion

**File:** `src/google_sheets.py`

Code tries service account from `credentials.json`, but README tells testers to create OAuth2 desktop credentials — these are incompatible flows.

**Fix:** Pick one and document it clearly. Recommended: Service Account (better for desktop/unattended). Update README to match.

---

### 10. Yelp date parsing returns wrong date for relative dates

**File:** `src/yelp_scraper.py` → `parse_date()`

"2 days ago" returns today instead of the actual inferred date.

```python
if "ago" in date_str.lower():
    return datetime.now().strftime("%Y-%m-%d")  # ← Wrong
```

**Fix:** Parse relative dates properly (e.g., `dateutil.parser` or manual parsing).

---

### 11. Bare `print()` instead of structured logging

**Files:** `src/ai_reply.py`, `src/yelp_scraper.py`, others

```python
print(f"[AI Reply] OpenAI call failed, using fallback: {e}")
print(f"Scraped {len(reviews)} reviews from Yelp")
```

No log levels, no structured fields, no machine-parseable output.

**Fix:** Replace all `print()` with the existing `logger` from `src/logger.py`.

---

## Medium — Fix Before v1.0

### 12. No batching — serial processing with no backoff

**File:** `src/workflow.py` → `run()`

One review at a time: generate → wait → post → wait. No batching, no exponential backoff, no dead-letter queue, no resume on crash.

**Fix:** Batch generation (e.g., 10 reviews at a time). Add `--resume` flag for checkpoint recovery.

---

### 13. No startup config validation

**File:** `app.py`, `src/config.py`

`settings.is_configured` exists but is never checked. App starts with all credentials missing, then fails mid-flow.

**Fix:** Validate required env vars on startup. Show clear error dialog listing missing fields. Disable buttons that require missing config.

---

### 14. `except: pass` silently swallows errors

**File:** `src/yelp_scraper.py`

Multiple locations: `except: continue`, `except Exception: pass`. Errors are lost forever.

**Fix:** Log every exception with context. Count skipped elements. Surface skip count in UI summary.

---

### 15. No unit tests

**Files:** `src/` — all modules

No tests for: `parse_rating`, `parse_date`, `normalize_review_key`, `should_reply`, `fallback_reply`, `StateStore`.

**Fix:** Add `tests/` with pytest. Target 80% coverage on `src/` modules.

---

## Quick Wins (Low Effort / High Impact)

| | Fix | Effort |
|---|---|---|
| L-01 | Add `--verify` flag to test Yelp scraping without saving | 1h |
| L-02 | Add `--export-csv` flag to export processed reviews | 1h |
| L-03 | Show in UI: "Skipped: N / Processed: M" after each run | 2h |
| L-04 | Add `--dry-run --verbose` to print AI prompt + reply | 1h |

---

## Recommended Sprint Order

```
Sprint 1 → Critical fixes (C-01 to C-05)
Sprint 2 → High reliability (H-01 to H-07, H-10, H-11)
Sprint 3 → Medium polish (M-01 to M-05)
Sprint 4 → Architecture review + load test + deployment guide
```

---

## Architecture Recommendation

If scale matters, consider:

```
[Desktop UI / CLI] → [Core Worker Service] → [SQLite DB]
                     → [Queue / Job Scheduler]
                     → [Google APIs / OpenAI]
                     → [Sheets as export only]
```

- Keep `app.py` as UI layer only
- Move business logic to `src/` modules (already mostly done)
- Replace JSON state with SQLite
- Keep Sheets for reporting only

---

## Scores

| Dimension | Score |
|---|---|
| Functionality | 6/10 |
| Reliability | 4/10 |
| Scalability | 2/10 |
| Production readiness | 3/10 |

**Verdict:** Good base for development. Not ready for scale or unattended production use.