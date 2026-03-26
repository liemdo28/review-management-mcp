# Review Management MCP Server

MCP server for managing Yelp and Google Business Profile reviews for Raw Sushi Bar and Bakudan Ramen.

## Features

- ✅ Fetch new reviews from Yelp and Google Business Profile
- ✅ Post responses to reviews automatically
- ✅ Safety checks for negative reviews (requires approval)
- ✅ Track response history
- ✅ Support for multiple restaurant locations
- ✅ Automated scheduling support

## Prerequisites

### API Access Requirements

Before you can use this MCP server, you need API access from both platforms:

#### Yelp API Access

1. **Basic API Access** (free - for reading reviews):
   - Go to https://www.yelp.com/developers/v3/manage_app
   - Create a new app
   - Get your API Key
   - **Note**: Free tier only returns 3 most recent reviews

2. **Partner API Access** (for responding to reviews):
   - Go to https://www.yelp.com/developers/documentation/v3/respond_to_reviews
   - Apply for Partner API access
   - Wait for approval (can take several weeks)

#### Google Business Profile API Access

1. **Create Google Cloud Project**:
   - Go to https://console.cloud.google.com/
   - Create a new project
   - Enable "Google My Business API"

2. **Apply for API Access**:
   - Visit the GBP API Contact Form
   - Select "Application for Basic API Access"
   - Fill out the form with your business details
   - Wait for Google's approval email (typically 1-2 weeks)

3. **Set up OAuth 2.0**:
   - Create OAuth 2.0 credentials in Google Cloud Console
   - Add authorized redirect URI
   - Get your Client ID and Client Secret
   - Generate a refresh token

### Business Setup

You also need to identify your business IDs on each platform:

**Yelp Business ID**:
- Go to https://www.yelp.com/biz/[your-business-url]
- The business ID is in the URL path

**Google Location ID**:
- Use the Google My Business API to list your locations
- Or find it in the Google Business Profile dashboard URL

## Installation

### 1. Install Dependencies

```bash
cd review-management-mcp
npm install
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Yelp Configuration
YELP_API_KEY=your_yelp_api_key_here
YELP_BUSINESS_ID_RAW_SUSHI=your_raw_sushi_business_id
YELP_BUSINESS_ID_BAKUDAN=your_bakudan_ramen_business_id

# Google Configuration
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REFRESH_TOKEN=your_google_refresh_token
GOOGLE_LOCATION_ID_RAW_SUSHI=accounts/123/locations/456
GOOGLE_LOCATION_ID_BAKUDAN=accounts/123/locations/789
```

### 3. Build the Server

```bash
npm run build
```

### 4. Test the Server

```bash
npm start
```

## Usage

### Available Tools

The MCP server provides these tools:

1. **`list_new_reviews`**
   - Fetch new reviews that haven't been responded to yet
   - Parameters:
     - `platform`: 'yelp' | 'google' | 'both' (default: 'both')
     - `restaurant`: 'raw-sushi' | 'bakudan-ramen' | 'both' (default: 'both')

2. **`list_all_reviews`**
   - List all recent reviews with filtering
   - Parameters:
     - `platform`: Platform filter
     - `restaurant`: Restaurant filter
     - `min_stars`, `max_stars`: Star rating filters
     - `since_date`: Date filter (ISO format)
     - `limit`: Max results (default: 20)

3. **`get_review_details`**
   - Get complete details for a specific review
   - Parameters:
     - `review_id`: Review identifier (required)
     - `platform`: 'yelp' | 'google' (required)

4. **`post_review_response`**
   - Post a response to a review
   - Parameters:
     - `review_id`: Review identifier (required)
     - `platform`: 'yelp' | 'google' (required)
     - `response_text`: The response to post (required)
     - `approved_by_owner`: Safety flag for 1-3 star reviews (default: false)

5. **`get_response_history`**
   - View history of posted responses
   - Parameters:
     - `since_date`: Filter by date (ISO format)
     - `limit`: Max results (default: 50)

### Example Workflow with Claude

Once the MCP server is running and connected to Claude:

```
You: Check for new reviews

Claude uses: list_new_reviews()
Claude: I found 3 new reviews:
- Raw Sushi Bar (Yelp): ⭐⭐⭐⭐⭐ from Jennifer - "Best sushi in town!..."
- Bakudan Ramen (Google): ⭐⭐⭐⭐ from Michael - "Great tonkotsu..."
- Raw Sushi Bar (Google): ⭐⭐ from Sarah - "Service was slow..."

Would you like me to generate responses using the restaurant-review-response skill?

You: Yes, generate and post responses

Claude:
1. Uses restaurant-review-response skill to generate personalized responses
2. For 5-star review: Calls post_review_response() immediately (auto-post)
3. For 4-star review: Calls post_review_response() immediately (auto-post)
4. For 2-star review: Shows you the draft response and asks for approval

Claude: I've posted responses to the positive reviews. For the 2-star review from Sarah,
here's the draft response:

[Shows draft]

Should I post this response? (I need your approval for negative reviews)

You: Yes, post it

Claude: Calls post_review_response() with approved_by_owner=true
✅ All responses posted!
```

## Integration with Claude

### Add to Claude Desktop Config

Edit your Claude desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add:

```json
{
  "mcpServers": {
    "review-management": {
      "command": "node",
      "args": ["/path/to/review-management-mcp/dist/index.js"],
      "env": {
        "YELP_API_KEY": "your_key_here",
        "YELP_BUSINESS_ID_RAW_SUSHI": "your_id_here",
        "YELP_BUSINESS_ID_BAKUDAN": "your_id_here",
        "GOOGLE_CLIENT_ID": "your_client_id",
        "GOOGLE_CLIENT_SECRET": "your_client_secret",
        "GOOGLE_REFRESH_TOKEN": "your_refresh_token",
        "GOOGLE_LOCATION_ID_RAW_SUSHI": "accounts/123/locations/456",
        "GOOGLE_LOCATION_ID_BAKUDAN": "accounts/123/locations/789"
      }
    }
  }
}
```

Restart Claude Desktop.

## Automated Scheduling

### Option 1: Claude Scheduled Task (Recommended)

Use Claude's create-shortcut skill to create a scheduled task:

```
You: Create a shortcut to check reviews daily at 9 AM

Claude will create a scheduled task that:
1. Runs list_new_reviews() at 9 AM daily
2. Uses restaurant-review-response skill to generate responses
3. Auto-posts 4-5 star responses
4. Sends you a notification if there are 1-3 star reviews needing approval
```

### Option 2: Cron Job (Unix/Linux/Mac)

Add to your crontab:

```bash
# Check reviews daily at 9 AM
0 9 * * * /path/to/check-reviews.sh
```

Create `check-reviews.sh`:

```bash
#!/bin/bash
cd /path/to/review-management-mcp
node dist/cli-check-reviews.js | mail -s "Daily Review Check" your@email.com
```

### Option 3: Windows Task Scheduler

Create a scheduled task in Windows Task Scheduler that runs:

```powershell
node C:\path\to\review-management-mcp\dist\cli-check-reviews.js
```

## Response History

The MCP server automatically tracks all responses in `response-history.json`:

```json
{
  "responses": [
    {
      "review_id": "abc123",
      "platform": "yelp",
      "response_text": "Thank you, Jennifer! We're thrilled...",
      "timestamp": "2026-02-11T09:15:00Z",
      "approved_by_owner": false
    }
  ],
  "last_updated": "2026-02-11T09:15:00Z"
}
```

View history with: `get_response_history()`

## Troubleshooting

### "Yelp response posting requires Partner API access"

You don't have Yelp Partner API access yet. Apply at:
https://www.yelp.com/developers/documentation/v3/respond_to_reviews

In the meantime, use the manual workflow to copy-paste responses.

### "Google API error: 401 Unauthorized"

Your OAuth token may have expired or is invalid. Regenerate a refresh token:

1. Go to Google OAuth Playground: https://developers.google.com/oauthplayground/
2. Select "Google My Business API v4"
3. Authorize and get a new refresh token
4. Update your `.env` file

### "Cannot find business ID"

Make sure your business IDs are correctly configured in `.env`.

For Yelp: Check the URL at https://www.yelp.com/biz/[your-business]
For Google: Use the API to list locations or check your dashboard URL

## Security Notes

- ⚠️ **Never commit your `.env` file** - it contains API credentials
- ✅ Add `.env` to your `.gitignore`
- ✅ Use environment variables for production deployments
- ✅ The server requires explicit approval for negative reviews (safety check)
- ✅ All responses are tracked in `response-history.json` for audit trail

## Cost Considerations

### Yelp
- Basic API: Free
- Partner API: Contact Yelp sales

### Google Business Profile API
- Free for basic usage
- Rate limits: 60 requests per minute per user

## Support

For issues:
1. Check the troubleshooting section above
2. Review the API documentation:
   - Yelp: https://www.yelp.com/developers/documentation/v3
   - Google: https://developers.google.com/my-business
3. Check that your API credentials are correctly configured

## License

MIT
