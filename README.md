# Google Review Auto Reply - Desktop App

A desktop application for automatically fetching restaurant reviews from **Google Business Profile** and **Yelp**, generating AI-powered replies using OpenAI, and saving everything to **Google Sheets**.

---

## Features

| Feature | Description |
|---|---|
| **Google Reviews Tab** | Fetch reviews via Google Business Profile API, generate & post AI replies |
| **Yelp Reviews Tab** | Scrape Yelp pages with Selenium, generate AI replies, save to Google Sheets |
| **DRY RUN Mode** | Preview everything without posting real replies |
| **AI Reply Generation** | GPT-4o-mini generates restaurant-appropriate replies |
| **Google Sheets Integration** | All reviews + AI replies saved to a shared spreadsheet |
| **Dark Theme UI** | Modern dark-themed Tkinter interface |

---

## Quick Start for Testers

### 1. Download & Run

```bash
# Clone the repo
git clone https://github.com/liemdo28/review-management-mcp.git
cd review-management-mcp

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Or use the pre-built `.exe`:

```
dist-new/ReviewAutoReply-v2.exe
```

### 2. Setup Environment

Create a `.env` file in the project root:

```env
# OpenAI
OPENAI_API_KEY=sk-your-openai-key

# Google OAuth (for Google Business Profile)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REFRESH_TOKEN=your-refresh-token
GOOGLE_ACCOUNT_ID=115468214193182088373

# Location IDs
GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON=13520279089747024075
GOOGLE_LOCATION_ID_BAKUDAN_BANDERA=9390782300587134823
GOOGLE_LOCATION_ID_BAKUDAN_RIM=4435485907466482087
GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK=1599829923443837201

# Config
OPENAI_MODEL=gpt-4o-mini
DRY_RUN=true
```

### 3. Google Sheets Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Enable **Google Sheets API** and **Google Drive API**
3. Create **Service Account** credentials → download as `credentials.json`
4. Place `credentials.json` in the project folder
5. In the app: click **Load credentials.json** → **Connect Sheets**
6. Share your Google Sheet with the service account email

Target Spreadsheet: https://docs.google.com/spreadsheets/d/1SRgHk2KukTyja0dY5JnbLIiTG9PQwtm17KexQZrEIyo

---

## Project Structure

```
review-management-mcp/
├── app.py                 # Desktop app entry point (Tkinter UI)
├── src/
│   ├── config.py          # Settings from .env
│   ├── logger.py          # Logging setup
│   ├── google_auth.py    # Google OAuth token refresh
│   ├── google_reviews.py  # GBP API: list reviews + post reply
│   ├── ai_reply.py        # OpenAI reply generation
│   ├── state_store.py     # Prevent duplicate replies (JSON)
│   ├── workflow.py        # Main Google workflow logic
│   ├── yelp_scraper.py    # Selenium-based Yelp scraper
│   └── google_sheets.py   # Google Sheets integration
├── requirements.txt       # Python dependencies
└── README.md
```

---

## How to Test

### Google Reviews Tab

1. Open the app → **Google Reviews** tab
2. Check **DRY RUN** (recommended for first test)
3. Click **Check Google Reviews**
4. Reviews appear in the list
5. Select a review → Reply Preview shows AI-generated response
6. Click **Copy Reply** to copy to clipboard

### Yelp Reviews Tab

1. Open the app → **Yelp Reviews** tab
2. Select a Yelp business URL from dropdown
3. Click **Load credentials.json** and load your Google credentials file
4. Click **Connect Sheets**
5. Set max reviews (default: 20)
6. Click **Scrape Yelp → Save to Sheets**
7. Reviews + AI replies are saved to Google Sheets

---

## Testing Checklist

- [ ] App launches without errors
- [ ] Google Reviews tab fetches reviews correctly
- [ ] AI replies are generated for reviews
- [ ] Reply preview displays correctly
- [ ] Copy to clipboard works
- [ ] Yelp Reviews tab loads
- [ ] Yelp URL dropdown shows options
- [ ] Google Sheets connection works
- [ ] Scraped reviews saved to Sheets
- [ ] DRY RUN mode works (no real replies posted)
- [ ] Error handling (wrong credentials, no API key)

---

## Known Limitations

1. **Yelp scraping**: Requires Chrome browser installed. Yelp may show CAPTCHA for frequent access.
2. **Google Sheets**: Requires `credentials.json` from Google Cloud Console.
3. **Google Reviews**: Requires valid OAuth refresh token with GBP API access.
4. **Rate Limits**: Both Yelp and Google have API rate limits.

---

## Report Bugs

Please report issues with:

- Error messages (screenshot or text)
- Steps to reproduce
- Expected vs actual behavior
- Your OS and Python version

---

## License

MIT