# Bug Report & Task List — Review Management Desktop App

> Generated from stress-test design review
> Reviewer: QA Team
> Date: 2026-03-30
> Severity Scale: **Critical / High / Medium / Low**

---

## CRITICAL — Must fix before production

---

### C-01: StateStore race condition — data corruption under concurrent load

**File:** `src/state_store.py`
**Severity:** Critical
**Type:** Bug

**Description:**
`StateStore` reads the entire JSON file into memory, then overwrites it on every `mark_processed()`. With multiple processes or concurrent threads, this causes race conditions and potential file corruption.

**Current code:**
```python
def mark_processed(self, review_key: str, action: str, reply_preview: str):
    self.data.setdefault("processed_reviews", {})[review_key] = {...}
    self.save()  # Full file overwrite every call
```

**Impact:**
- Review may be processed twice (lost update)
- File may corrupt if two processes write simultaneously
- With 500k reviews, file becomes gigabytes and slow

**Fix:**
- Replace with SQLite: `import sqlite3` + proper transaction
- Or at minimum: use file locking with `fcntl`/`msvcrt`

**Status:** TODO

---

### C-02: Google Sheets bottleneck — O(n) read on every save

**File:** `src/google_sheets.py`
**Severity:** Critical
**Type:** Performance Bug

**Description:**
`save_reviews_to_sheet` calls `sheet.col_values(1)` to read ALL existing review IDs into memory on every save. With 1000+ rows, this becomes extremely slow.

```python
existing = sheet.col_values(1)  # Reads entire column every time
existing_ids = set(existing[1:])
```

And `update_review_reply_status` uses `find()` which scans the entire sheet.

**Impact:**
- Sheets becomes unusable at scale
- Google Sheets API has 60 req/min limit — will hit immediately
- App appears frozen or timed out

**Fix:**
- Batch inserts (up to 100 rows per API call)
- Cache known IDs in memory on startup
- Switch to database as primary store, Sheets as read-only export

**Status:** TODO

---

### C-03: DRY RUN metrics bug — "Replied: 0" misleads users

**File:** `src/workflow.py`
**Severity:** Critical
**Type:** Logic Bug

**Description:**
When `DRY_RUN=true`, reviews are marked processed and AI replies are generated, but `total_replied` counter is NOT incremented. UI shows "Replied: 0" even after successfully generating 20 replies.

```python
if effective_dry_run:
    logger.info("DRY_RUN enabled. Not posting reply.")
    state_store.mark_processed(review_key, "dry_run_generated", reply_text)
    continue  # ← Skips total_replied += 1
```

**Impact:**
- Testers/owners think replies failed when they didn't
- Makes DRY RUN mode appear broken in the UI

**Fix:**
- Add `total_generated` counter for DRY RUN
- Or show "Generated: N / Replied: M" split in UI

**Status:** TODO

---

### C-04: Yelp scraper — brittle CSS selectors break on DOM change

**File:** `src/yelp_scraper.py`
**Severity:** Critical
**Type:** Reliability Bug

**Description:**
Yelp HTML structure changes frequently. CSS selectors like `[data-review-id]`, `.review`, `[class*='user']`, `[class*='date']` will silently return empty results or wrong data when Yelp updates their UI.

```python
rating_elem = elem.find_element(By.CSS_SELECTOR, "[aria-label*='star'], .i-stars--active, [class*='stars']")
# All of these are fragile string matching on class names
```

Also: `except: continue` silently swallows all errors.

**Impact:**
- App stops returning reviews with zero error signal
- User sees empty list with no explanation
- CAPTCHA detection will also cause silent failure

**Fix:**
- Add schema validation for each scraped review
- Raise exceptions on critical field failures
- Add logging for every skip/retry
- Add `--verify` flag to test scraping without saving

**Status:** TODO

---

### C-05: Google tab UI logging completely missing

**File:** `app.py`
**Severity:** Critical
**Type:** Missing Feature / UX Bug

**Description:**
`_log_google()` is defined but contains only `pass`. Progress during Google workflow is invisible to users.

```python
def _log_google(self, msg: str):
    pass  # ← Nothing happens
```

**Impact:**
- User doesn't know if app is running or stuck
- No error visibility
- Appears frozen during API calls

**Fix:**
- Wire `_log_google` to a ScrolledText widget in the Google tab
- Add progress indicators during loops

**Status:** TODO

---

## HIGH — Fix before beta/internal release

---

### H-01: Yelp AI reply uses generic "Restaurant" name

**File:** `app.py` → `scrape_yelp_to_sheets()`
**Severity:** High
**Type:** Quality Bug

**Description:**
When generating AI replies for Yelp reviews, the code passes hardcoded values instead of real business name:

```python
reply = generate_ai_reply(
    review={...},
    restaurant_name="Restaurant",  # ← Always "Restaurant"
    location="",                   # ← Always empty
    ...
)
```

**Fix:**
- Parse business name from Yelp page during scrape
- Pass selected URL from dropdown as lookup key to get real name

**Status:** TODO

---

### H-02: Google Sheets auth — OAuth2 vs Service Account confusion

**File:** `src/google_sheets.py`
**Severity:** High
**Type:** Design Bug / Documentation Bug

**Description:**
Code supports both OAuth2 and Service Account but the README tells testers to create OAuth2 desktop credentials while the code prioritizes Service Account from `credentials.json`. These are incompatible flows.

```python
# Code does this:
creds = service_account.Credentials.from_service_account_file(...)  # Service Account

# README says:
# "Create OAuth2 credentials (Desktop app)"
```

**Fix:**
- Pick ONE auth method and document it consistently
- Recommended: Service Account (simpler for unattended/desktop app)
- Update README to match actual code flow

**Status:** TODO

---

### H-03: Yelp `on_yelp_select` is a stub — no row detail preview

**File:** `app.py`
**Severity:** High
**Type:** Missing Feature

**Description:**
Clicking a row in the Yelp tree does nothing. The `on_yelp_select` handler is incomplete:

```python
def on_yelp_select(self, _):
    sel = self.tree_yelp.selection()
    if not sel:
        return
    idx = self.tree_yelp.index(sel[0])
    # Get from the tree data (simplified for now)  ← NEVER IMPLEMENTED
```

**Fix:**
- Store full review objects alongside tree rows
- Show full review text + AI reply in preview area when row selected

**Status:** TODO

---

### H-04: Google tree selection — no reply preview on click

**File:** `app.py`
**Severity:** High
**Type:** Missing Feature

**Description:**
Google tab's `tree_google` has no click handler bound. Selecting a row doesn't show the reply text in `reply_text_google`.

**Fix:**
- Bind `<<TreeviewSelect>>` event to a handler
- Populate `reply_text_google` with the selected review's AI reply

**Status:** TODO

---

### H-05: Yelp `parse_date` — "2 days ago" returns today

**File:** `src/yelp_scraper.py`
**Severity:** High
**Type:** Data Quality Bug

**Description:**
Relative dates like "2 days ago" are returned as today's date instead of the actual date:

```python
if "ago" in date_str.lower():
    return datetime.now().strftime("%Y-%m-%d")  # ← Wrong for 2 days ago
```

**Fix:**
- Parse relative date strings properly
- Or at minimum: show in UI that this is an approximation

**Status:** TODO

---

### H-06: No structured logging — `print()` everywhere

**File:** Multiple files
**Severity:** High
**Type:** Observability Bug

**Description:**
Uses bare `print()` calls throughout code. No log levels, no structured fields, no machine-parseable output:

```python
print(f"[AI Reply] OpenAI call failed, using fallback: {e}")
print(f"Scraped {len(reviews)} reviews from Yelp")
```

**Fix:**
- Use the existing `logger` from `src/logger.py` everywhere
- Add structured fields (JSON) for programmatic log parsing
- Add log level configuration from env

**Status:** TODO

---

## MEDIUM — Fix before v1.0 release

---

### M-01: Workflow runs serially — no batching, no backoff

**File:** `src/workflow.py`
**Severity:** Medium
**Type:** Performance / Scalability

**Description:**
`run()` processes reviews one at a time with no batching:
- Generates 1 AI reply → waits → posts 1 reply → waits
- No exponential backoff on rate limits
- No dead-letter queue for failed items
- No resume capability if app crashes mid-run

**Fix:**
- Batch reviews (e.g., generate 10 AI replies in parallel, then post)
- Add exponential backoff
- Add `--resume` flag to continue from last checkpoint

**Status:** TODO

---

### M-02: No config validation on startup

**File:** `app.py`, `src/config.py`
**Severity:** Medium
**Type:** UX / Robustness

**Description:**
`settings.is_configured` exists but is never checked. App starts even with all credentials missing, then fails silently or crashes on first button press.

**Fix:**
- Validate required env vars on startup
- Show clear error dialog with missing fields listed
- Disable buttons that require missing config

**Status:** TODO

---

### M-03: Yelp dropdown URL mismatch — URLs not verified

**File:** `app.py`
**Severity:** Medium
**Type:** Data Quality

**Description:**
`YELP_URLS` dictionary has hardcoded URLs that may be outdated or wrong. No URL validation before scrape.

```python
YELP_URLS = {
    "bakudan-bandera": "https://www.yelp.com/biz/bakudan-ramen-san-antonio",  # ← May not be the right URL
}
```

**Fix:**
- Validate URLs return 200 before scrape
- Add URL input field so users can paste any Yelp URL
- Show scrapeable URL count in dropdown

**Status:** TODO

---

### M-04: Silent `except: pass` in Yelp scraper

**File:** `src/yelp_scraper.py`
**Severity:** Medium
**Type:** Debuggability

**Description:**
Multiple bare `except: continue` that silently swallow errors without any logging:

```python
except Exception as e:
    continue  # ← Error lost forever
```

**Fix:**
- Log every skipped element with reason
- Count skipped vs successful
- Surface skip count in UI summary

**Status:** TODO

---

### M-05: No unit tests for critical logic

**File:** Multiple
**Severity:** Medium
**Type:** Quality / Test Coverage

**Missing tests for:**
- `parse_rating()` — star string → int
- `parse_date()` — Yelp date → ISO
- `normalize_review_key()` — review → stable ID
- `should_reply()` — skip logic
- `fallback_reply()` — AI fallback
- `StateStore` — add/get/reset

**Fix:**
- Add `tests/` folder with pytest
- Target: 80% coverage on `src/` modules

**Status:** TODO

---

## LOW — Nice to have

---

### L-01: Add `--verify` CLI mode to test scraping without saving
### L-02: Add `--export-csv` flag to export processed reviews
### L-03: Add notification (system tray / email) on negative reviews
### L-04: Add `--dry-run --verbose` to show AI prompt + reply
### L-05: Custom prompt override via env var for AI replies

---

## Summary Dashboard

| ID | Severity | File | Issue | Status |
|----|----------|------|-------|--------|
| C-01 | **CRITICAL** | state_store.py | JSON race condition | TODO |
| C-02 | **CRITICAL** | google_sheets.py | O(n) read on every save | TODO |
| C-03 | **CRITICAL** | workflow.py | DRY RUN counter bug | TODO |
| C-04 | **CRITICAL** | yelp_scraper.py | Brittle CSS selectors | TODO |
| C-05 | **CRITICAL** | app.py | Google log missing | TODO |
| H-01 | **HIGH** | app.py | Generic "Restaurant" in AI reply | TODO |
| H-02 | **HIGH** | google_sheets.py | OAuth/SA confusion | TODO |
| H-03 | **HIGH** | app.py | Yelp row selection stub | TODO |
| H-04 | **HIGH** | app.py | Google row selection stub | TODO |
| H-05 | **HIGH** | yelp_scraper.py | Wrong relative dates | TODO |
| H-06 | **HIGH** | Multiple | Bare print() everywhere | TODO |
| M-01 | MEDIUM | workflow.py | Serial processing, no batching | TODO |
| M-02 | MEDIUM | app.py | No startup config validation | TODO |
| M-03 | MEDIUM | app.py | Unverified Yelp URLs | TODO |
| M-04 | MEDIUM | yelp_scraper.py | Silent except: pass | TODO |
| M-05 | MEDIUM | tests/ | No unit tests | TODO |
| L-01–05 | LOW | Various | Nice-to-have | TODO |

---

## Recommended Sprint Order

**Sprint 1 (Critical fixes):** C-01 → C-02 → C-03 → C-04 → C-05
**Sprint 2 (High reliability):** H-01 → H-02 → H-03 → H-04 → H-05 → H-06
**Sprint 3 (Medium polish):** M-01 → M-02 → M-03 → M-04 → M-05
**Sprint 4 (Production readiness):** Architecture review, load test, deployment guide

---

## v3 Fixed Issues — commit `3ca5ee7`

### ✅ Critical Fixed (5/5)
- **C-01**: StateStore → SQLite WAL mode, atomic transactions, indexes
- **C-02**: Sheets = export-only, batch 100 rows/call, rate-limit backoff
- **C-03**: DRY RUN increments `total_generated` (not `total_replied`)
- **C-04**: Yelp scraper has schema validation + structured logging + ScrapingError
- **C-05**: Google tab log wired to ScrolledText + progress callbacks

### ✅ High Fixed (6/6)
- **H-01**: Yelp AI prompt uses `YELP_REGISTRY` real business names
- **H-02**: Sheets auth = Service Account only (OAuth2 removed)
- **H-03**: Yelp row click shows full AI reply in preview panel
- **H-04**: Google row click shows review text + reply preview
- **H-05**: `parse_date` handles "3 days ago" / "2 weeks ago" correctly
- **H-06**: All `print()` → `logger` from `src/logger.py`

### ✅ Medium Fixed (3/5)
- **M-02**: `validate_config()` at startup → error dialog with missing fields
- **M-04**: No silent `except: pass` — all errors logged with context
- **M-05**: **28 unit tests in `tests/test_src.py`, 100% pass rate**

### ⏳ Not Fixed Yet
- **M-01**: Serial processing / no batching (future sprint)
- **M-03**: Yelp URL pre-validation (future sprint)
- **L-01..L-05**: Nice-to-haves (future sprint)
