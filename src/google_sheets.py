"""
Google Sheets integration for storing and managing reviews.
Uses gspread library with OAuth2 credentials.
"""

import os
import json
from datetime import datetime
from typing import Any
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import gspread

# Google Sheets scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


class SheetsConfig:
    """Configuration for Google Sheets integration."""

    # Your spreadsheet URL: https://docs.google.com/spreadsheets/d/1SRgHk2KukTyja0dY5JnbLIiTG9PQwtm17KexQZrEIyo/edit
    SPREADSHEET_ID = "1SRgHk2KukTyja0dY5JnbLIiTG9PQwtm17KexQZrEIyo"

    # Credentials file (OAuth2 JSON from Google Cloud Console)
    CREDENTIALS_FILE = "credentials.json"

    # Token file (auto-generated after first auth)
    TOKEN_FILE = "token.json"

    # Sheet names
    REVIEWS_SHEET = "Reviews"
    RESPONSES_SHEET = "Responses"
    SETTINGS_SHEET = "Settings"


def get_gspread_client() -> gspread.Client:
    """
    Get authenticated gspread client.
    Handles both OAuth2 and Service Account authentication.
    """
    creds = None

    # Method 1: Try loading existing token
    if os.path.exists(SheetsConfig.TOKEN_FILE):
        creds = Credentials.from_authorized_user_info(
            json.load(open(SheetsConfig.TOKEN_FILE)),
            SCOPES
        )

    # Method 2: Try service account credentials
    if not creds or not creds.valid:
        if os.path.exists(SheetsConfig.CREDENTIALS_FILE):
            creds = service_account.Credentials.from_service_account_file(
                SheetsConfig.CREDENTIALS_FILE, scopes=SCOPES
            )
            return gspread.authorize(creds)

    # Method 3: Try refreshing
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Save refreshed token
        with open(SheetsConfig.TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    if not creds or not creds.valid:
        raise Exception(
            "No valid Google credentials found. Please set up:\n"
            "1. Download OAuth2 credentials from Google Cloud Console\n"
            "2. Save as 'credentials.json' in the app folder\n"
            "OR create a Service Account and save as 'service_account.json'"
        )

    return gspread.authorize(creds)


def get_or_create_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """
    Get the spreadsheet by ID, or create a new one if it doesn't exist.
    """
    try:
        spreadsheet = client.open_by_key(SheetsConfig.SPREADSHEET_ID)
        print(f"Opened existing spreadsheet: {spreadsheet.title}")
        return spreadsheet
    except gspread.SpreadsheetNotFound:
        print(f"Spreadsheet not found. Creating new spreadsheet...")
        spreadsheet = client.create("Review Management - Auto Reply")

        # Share with the email from credentials
        try:
            spreadsheet.share("", perm_type="anyone", role="writer")
            print(f"Created and shared new spreadsheet: {spreadsheet.id}")
        except:
            pass

        return spreadsheet


def setup_sheets(spreadsheet: gspread.Spreadsheet) -> None:
    """
    Set up the spreadsheet with proper headers and formatting.
    Creates sheets if they don't exist.
    """
    # Create Reviews sheet
    try:
        reviews_sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)
    except gspread.WorksheetNotFound:
        reviews_sheet = spreadsheet.add_worksheet(
            SheetsConfig.REVIEWS_SHEET, rows=1000, cols=10
        )
        # Set headers
        reviews_sheet.update(
            "A1:J1",
            [["ID", "Source", "Business", "Reviewer", "Rating", "Date",
              "Review Text", "Reply Status", "AI Reply", "Scraped At"]]
        )
        # Format header row
        reviews_sheet.format("A1:J1", {
            "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })

    # Create Responses sheet
    try:
        responses_sheet = spreadsheet.worksheet(SheetsConfig.RESPONSES_SHEET)
    except gspread.WorksheetNotFound:
        responses_sheet = spreadsheet.add_worksheet(
            SheetsConfig.RESPONSES_SHEET, rows=1000, cols=8
        )
        responses_sheet.update(
            "A1:H1",
            [["Review ID", "Source", "Business", "Reviewer", "Rating",
              "Original Review", "AI Response", "Posted At"]]
        )
        responses_sheet.format("A1:H1", {
            "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.2},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}
        })

    print("Sheets setup complete!")


def save_reviews_to_sheet(spreadsheet: gspread.Spreadsheet, reviews: list[dict[str, Any]]) -> int:
    """
    Save reviews to the Reviews sheet.
    Appends new reviews, skips duplicates based on review ID.
    """
    try:
        sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)
    except gspread.WorksheetNotFound:
        setup_sheets(spreadsheet)
        sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)

    # Get existing review IDs to avoid duplicates
    existing_ids = set()
    try:
        existing = sheet.col_values(1)  # Column A = ID
        existing_ids = set(existing[1:])  # Skip header
    except:
        pass

    # Filter new reviews
    new_reviews = [r for r in reviews if r.get("id", "") not in existing_ids]

    if not new_reviews:
        print(f"No new reviews to save (all {len(reviews)} already exist)")
        return 0

    # Prepare rows
    rows = []
    for r in new_reviews:
        rating_display = "⭐" * r.get("rating", 0)
        rows.append([
            r.get("id", ""),
            r.get("source", ""),
            r.get("business_name", ""),
            r.get("reviewer_name", ""),
            rating_display,
            r.get("date", ""),
            r.get("text", "")[:500],  # Truncate long text
            r.get("reply_status", "Pending"),
            r.get("ai_reply", ""),
            r.get("scraped_at", ""),
        ])

    # Append to sheet
    if rows:
        sheet.append_rows(rows)
        print(f"Saved {len(rows)} new reviews to Google Sheets")

    return len(rows)


def save_response_to_sheet(
    spreadsheet: gspread.Spreadsheet,
    review_id: str,
    source: str,
    business_name: str,
    reviewer_name: str,
    rating: int,
    original_review: str,
    ai_response: str,
) -> None:
    """Save a response to the Responses sheet."""
    try:
        sheet = spreadsheet.worksheet(SheetsConfig.RESPONSES_SHEET)
    except gspread.WorksheetNotFound:
        setup_sheets(spreadsheet)
        sheet = spreadsheet.worksheet(SheetsConfig.RESPONSES_SHEET)

    rating_display = "⭐" * rating

    sheet.append_row([
        review_id,
        source,
        business_name,
        reviewer_name,
        rating_display,
        original_review[:500],
        ai_response,
        datetime.now().isoformat(),
    ])

    # Also update the Reviews sheet
    try:
        reviews_sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)
        # Find the row with this review ID and update reply status
        cell = reviews_sheet.find(review_id)
        if cell:
            reviews_sheet.update_cell(cell.row, 8, "Replied")  # Column H = Reply Status
            reviews_sheet.update_cell(cell.row, 9, ai_response[:500])  # Column I = AI Reply
    except:
        pass


def get_all_reviews(spreadsheet: gspread.Spreadsheet) -> list[dict[str, Any]]:
    """Get all reviews from the Reviews sheet."""
    try:
        sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)
        records = sheet.get_all_records()
        return list(records)
    except gspread.WorksheetNotFound:
        return []


def update_review_reply_status(
    spreadsheet: gspread.Spreadsheet,
    review_id: str,
    ai_reply: str,
    status: str = "Ready",
) -> bool:
    """Update the reply status and AI reply for a review."""
    try:
        sheet = spreadsheet.worksheet(SheetsConfig.REVIEWS_SHEET)
        cell = sheet.find(review_id)
        if cell:
            sheet.update_cell(cell.row, 8, status)  # Column H
            sheet.update_cell(cell.row, 9, ai_reply[:500])  # Column I
            return True
    except:
        pass
    return False


if __name__ == "__main__":
    # Test connection
    print("Testing Google Sheets connection...")
    try:
        client = get_gspread_client()
        spreadsheet = get_or_create_spreadsheet(client)
        setup_sheets(spreadsheet)
        print(f"Connected to: {spreadsheet.title}")
        print(f"Spreadsheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")
    except Exception as e:
        print(f"Connection failed: {e}")
        print("\nTo set up Google Sheets integration:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a project or select existing one")
        print("3. Enable Google Sheets API and Google Drive API")
        print("4. Create OAuth2 credentials (Desktop app)")
        print("5. Download and save as 'credentials.json' in the app folder")