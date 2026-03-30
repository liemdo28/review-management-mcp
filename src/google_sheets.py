"""
Google Sheets integration — EXPORT ONLY, not primary data store.

Design principles:
- Primary data lives in SQLite (StateStore)
- Sheets = read-only reporting / export target
- Batched writes (up to 100 rows/API call)
- Rate-limit backoff
- Service Account auth ONLY (no OAuth2 confusion)

Auth setup:
1. Go to console.cloud.google.com
2. Enable Google Sheets API + Google Drive API
3. Create a Service Account
4. Download JSON key → save as credentials.json in app folder
5. Share the spreadsheet with the service account email
"""

import os
import time
import logging
from datetime import datetime
from typing import Any

import gspread
from google.oauth2 import service_account

logger = logging.getLogger("review_bot")

# ── Config ─────────────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1SRgHk2KukTyja0dY5JnbLIiTG9PQwtm17KexQZrEIyo"
SERVICE_ACCOUNT_FILE = "credentials.json"
SHEET_REVIEWS = "Reviews"
SHEET_RESPONSES = "Responses"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# Sheets API limits
BATCH_SIZE = 100          # rows per API call
RATE_LIMIT_DELAY = 1.1   # seconds between batches (Sheets = 60 req/min)
MAX_RETRIES = 3


# ── Auth ───────────────────────────────────────────────────────────────────────

def _get_client() -> gspread.Client:
    """
    Returns authenticated gspread client using Service Account.
    Raises clear error if credentials are missing/invalid.
    """
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(
            f"Service Account credentials not found.\n"
            f"Expected file: {SERVICE_ACCOUNT_FILE}\n"
            f"Download from: Google Cloud Console → IAM → Service Accounts → Keys\n"
            f"Share spreadsheet with the service account email first."
        )

    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        client = gspread.authorize(creds)
        logger.info("Google Sheets client authenticated (Service Account)")
        return client
    except Exception as e:
        raise RuntimeError(
            f"Failed to authenticate with Google Sheets: {e}\n"
            f"Verify: (1) credentials.json is valid, "
            f"(2) Sheets API is enabled, "
            f"(3) spreadsheet is shared with service account email."
        ) from e


# ── Spreadsheet access ─────────────────────────────────────────────────────────

def get_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """Open spreadsheet by ID."""
    try:
        return client.open_by_key(SPREADSHEET_ID)
    except gspread.SpreadsheetNotFound:
        raise gspread.SpreadsheetNotFound(
            f"Spreadsheet '{SPREADSHEET_ID}' not found.\n"
            f"Create it at: https://docs.google.com/spreadsheets/create"
        )


def _get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet, name: str, headers: list[str]
) -> gspread.Worksheet:
    """Get existing worksheet or create with headers."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(name, rows=1000, cols=len(headers))
        ws.update("A1", [headers])
        ws.format("A1", {
            "backgroundColor": {"red": 0.15, "green": 0.35, "blue": 0.65},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })
        logger.info(f"Created worksheet: {name}")
        return ws


def ensure_sheets(spreadsheet: gspread.Spreadsheet) -> None:
    """Ensure both required worksheets exist with correct headers."""
    _get_or_create_worksheet(
        spreadsheet, SHEET_REVIEWS,
        ["Review ID", "Source", "Location", "Reviewer", "Rating",
         "Date", "Review Text (truncated)", "Status", "AI Reply", "Processed At"]
    )
    _get_or_create_worksheet(
        spreadsheet, SHEET_RESPONSES,
        ["Review ID", "Source", "Location", "Reviewer", "Rating",
         "Original Review", "AI Response", "Posted At"]
    )
    logger.info("All sheets verified.")


# ── Core export functions ───────────────────────────────────────────────────────

def export_reviews_to_sheet(
    spreadsheet: gspread.Spreadsheet,
    reviews: list[dict[str, Any]],
    on_progress: callable = None,
) -> dict[str, int]:
    """
    Batch-export reviews to the Reviews sheet.

    Data is already in SQLite — this only writes to Sheets for reporting.
    Batches rows to stay within Sheets rate limits.

    Args:
        spreadsheet: open gspread Spreadsheet object
        reviews: list of review dicts (from SQLite or workflow)
        on_progress: optional callback(str) for UI updates

    Returns:
        {"exported": N, "skipped": M, "errors": K}
    """
    if not reviews:
        logger.info("No reviews to export to Sheets")
        return {"exported": 0, "skipped": 0, "errors": 0}

    sheet = _get_or_create_worksheet(
        spreadsheet, SHEET_REVIEWS,
        ["Review ID", "Source", "Location", "Reviewer", "Rating",
         "Date", "Review Text (truncated)", "Status", "AI Reply", "Processed At"]
    )

    # Get current row count for append position (cached, not re-read every row)
    try:
        row_count = int(sheet.acell("A1").value or 1)
        if row_count < 1:
            row_count = 1
    except Exception:
        row_count = 1  # fallback: start from row 1 (after header)

    results = {"exported": 0, "skipped": 0, "errors": 0}
    batch: list[list] = []

    for i, r in enumerate(reviews):
        try:
            rating = r.get("rating", 0)
            stars = "⭐" * (rating if isinstance(rating, int) else 0)

            row = [
                str(r.get("review_key", "")),
                str(r.get("source", "")),
                str(r.get("location_name", "")),
                str(r.get("reviewer_name", "")),
                stars,
                str(r.get("date", "")),
                (r.get("text", "") or "")[:500],
                str(r.get("status", "Pending")),
                (r.get("ai_reply", "") or "")[:500],
                str(r.get("processed_at", "")),
            ]
            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                _write_batch(sheet, row_count, batch)
                results["exported"] += len(batch)
                row_count += len(batch)
                batch = []

                msg = f"Exported {results['exported']}/{len(reviews)} reviews to Sheets..."
                logger.info(msg)
                if on_progress:
                    on_progress(msg)

        except Exception as e:
            results["errors"] += 1
            logger.error(f"Failed to prepare row for review {r.get('review_key', '?')}: {e}")

    # Flush remaining batch
    if batch:
        try:
            _write_batch(sheet, row_count, batch)
            results["exported"] += len(batch)
        except Exception as e:
            results["errors"] += len(batch)
            logger.error(f"Batch write failed: {e}")

    logger.info(
        f"Sheets export done: exported={results['exported']} "
        f"skipped={results['skipped']} errors={results['errors']}"
    )
    return results


def _write_batch(
    sheet: gspread.Worksheet,
    start_row: int,
    rows: list[list],
) -> None:
    """Write a batch of rows with retry + backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            end_row = start_row + len(rows) - 1
            range_str = f"A{start_row}:J{end_row}"
            sheet.update(range_str, rows)
            time.sleep(RATE_LIMIT_DELAY)  # respect rate limits
            return
        except gspread.exceptions.APIError as e:
            if e.response and e.response.status_code == 429:
                wait = (attempt + 1) * 2.0
                logger.warning(f"Sheets rate limit hit, backing off {wait}s...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"Batch write failed after {MAX_RETRIES} retries: {e}") from e
            time.sleep(1)


def export_response(
    spreadsheet: gspread.Spreadsheet,
    review_id: str,
    source: str,
    location_name: str,
    reviewer_name: str,
    rating: int,
    original_review: str,
    ai_response: str,
) -> bool:
    """Export a single posted response to the Responses sheet."""
    try:
        sheet = _get_or_create_worksheet(
            spreadsheet, SHEET_RESPONSES,
            ["Review ID", "Source", "Location", "Reviewer", "Rating",
             "Original Review", "AI Response", "Posted At"]
        )

        row = [
            review_id,
            source,
            location_name,
            reviewer_name,
            "⭐" * rating,
            original_review[:500],
            ai_response,
            datetime.now().isoformat(),
        ]

        for attempt in range(MAX_RETRIES):
            try:
                sheet.append_row(row)
                time.sleep(RATE_LIMIT_DELAY)
                return True
            except gspread.exceptions.APIError as e:
                if e.response and e.response.status_code == 429:
                    time.sleep((attempt + 1) * 2.0)
                else:
                    raise

    except Exception as e:
        logger.error(f"Failed to export response for {review_id}: {e}")
        return False


# ── Connection helper ─────────────────────────────────────────────────────────

def connect() -> tuple[gspread.Client, gspread.Spreadsheet]:
    """
    One-call connect: returns (client, spreadsheet).
    Use this in app.py instead of calling individual functions.
    """
    client = _get_client()
    spreadsheet = get_spreadsheet(client)
    ensure_sheets(spreadsheet)
    return client, spreadsheet


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    logger.setLevel(logging.INFO)

    print("Testing Google Sheets connection...")
    try:
        client, spreadsheet = connect()
        print(f"✅ Connected to: {spreadsheet.title}")
        print(f"   URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n📋 Setup guide:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Enable Google Sheets API + Google Drive API")
        print("3. IAM → Service Accounts → Create (or use existing)")
        print("4. Keys → Add Key → JSON → download")
        print("5. Save as 'credentials.json' in the app folder")
        print("6. Share the spreadsheet with the service account email")
    except Exception as e:
        print(f"❌ Connection failed: {e}")