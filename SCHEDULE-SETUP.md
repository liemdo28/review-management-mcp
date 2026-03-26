# Automated Review Responder — Setup Guide

## What this does
Every 12 hours (8am + 8pm), Claude Haiku automatically:
- Checks all 4 locations for new unresponded reviews
- **4-5 ★** → posts a warm, personalized response immediately
- **1-3 ★** → drafts a response and saves it to `logs/pending-reviews.md` for your approval

---

## Step 1 — Build the MCP server

```bash
cd ~/path/to/review-management-mcp   # wherever the project lives
npm install && npm run build
```

Then restart Claude Desktop so it picks up the Bakudan locations.

---

## Step 2 — Make scripts executable

```bash
chmod +x ~/path/to/review-management-mcp/scripts/auto-respond.sh
chmod +x ~/path/to/review-management-mcp/scripts/setup-cli-mcp.sh
chmod +x ~/path/to/review-management-mcp/scripts/test-connection.mjs
```

---

## Step 3 — Test the connection (identify Bakudan locations)

```bash
node ~/path/to/review-management-mcp/scripts/test-connection.mjs
```

This lists all locations with full street addresses so you can identify which
Bakudan ID maps to Stone Oak / Bandera / Rim. Once confirmed, update the
`.env` variable names and `src/index.ts` display names accordingly, then
rebuild (`npm run build`).

---

## Step 4 — Test the auto-responder manually

The auto-respond.sh is **self-contained** — it reads `.env` directly and
builds its own MCP config at runtime. No separate MCP registration needed.

```bash
~/path/to/review-management-mcp/scripts/auto-respond.sh
```

Check `logs/auto-respond.log` to see what it did. If successful, you'll see
Haiku reporting how many reviews it auto-posted and how many drafts it saved.

---

## Step 5 — (Optional) Register MCP globally for CLI use

If you want to use the review tools in any Claude CLI session (not just
the scheduled script), run this once:

```bash
~/path/to/review-management-mcp/scripts/setup-cli-mcp.sh
```

Verify with:
```bash
claude mcp list
```

---

## Step 6 — Install the launchd scheduler (runs every 12 hours)

1. Edit the `.plist` file — update the 3 paths that say `/Users/hoangle/review-management-mcp/...` to match your actual project location.

2. Copy to LaunchAgents:
   ```bash
   cp launchd/com.rawsushi.review-responder.plist ~/Library/LaunchAgents/
   ```

3. Load it:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.rawsushi.review-responder.plist
   ```

4. Confirm it's scheduled:
   ```bash
   launchctl list | grep rawsushi
   ```

---

## Day-to-day workflow

| What | Where |
|------|-------|
| Auto-posted responses | Google Business Profile (live) |
| Pending 1-3★ drafts | `logs/pending-reviews.md` |
| Full activity log | `logs/auto-respond.log` |
| Run Claude now | `launchctl start com.rawsushi.review-responder` |
| Stop scheduler | `launchctl unload ~/Library/LaunchAgents/com.rawsushi.review-responder.plist` |

---

## Approving pending low-star reviews

When you see a notification that `pending-reviews.md` has new entries:
1. Open Claude and say: **"check pending reviews"**
2. Claude will show you the drafts and post the ones you approve

---

## Locations configured

| Key | Location | ID |
|-----|----------|----|
| `raw-sushi-stockton` | Raw Sushi Bistro (Stockton) | 13520279089747024075 |
| `bakudan-1` | Bakudan Ramen (SA-1) | 9390782300587134823 |
| `bakudan-2` | Bakudan Ramen (SA-2) | 4435485907466482087 |
| `bakudan-3` | Bakudan Ramen (SA-3) | 1599829923443837201 |

> **Note:** The 3 Bakudan IDs are assigned in the order Google returned them.
> Run `test-connection.mjs` with street addresses to verify which is
> Stone Oak / Bandera / Rim, then update `.env` and `src/index.ts` names.

---

## Troubleshooting

**"dist/index.js not found"** → Run `npm run build` first.

**Haiku says it can't access MCP tools** → Check `logs/auto-respond.log` for
the line `MCP config written to: /tmp/review-mcp-XXXXX.json`. If that line
appears, the config was built. If Haiku still fails, check that `.env` has all
required keys (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, etc.).

**launchd not running the script** → Check `logs/launchd-err.log` and make
sure the path in the `.plist` matches where your project actually lives.
