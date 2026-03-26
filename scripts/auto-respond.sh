#!/bin/bash
# =============================================================================
# auto-respond.sh — Automated restaurant review responder
# Runs every 12 hours via launchd. Uses Claude (Haiku) with the
# review-management MCP to auto-post 4-5★ replies and save 1-3★
# drafts to pending-reviews.md for owner approval.
#
# SELF-CONTAINED: builds its own --mcp-config at runtime from .env,
# so no separate MCP registration step is required.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/auto-respond.log"
PENDING_FILE="$PROJECT_DIR/logs/pending-reviews.md"
DIST_JS="$PROJECT_DIR/dist/index.js"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$PROJECT_DIR/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Review auto-responder starting ==="

# ── Validate dist/index.js exists ───────────────────────────────────────────

if [[ ! -f "$DIST_JS" ]]; then
  log "ERROR: $DIST_JS not found. Run 'npm run build' inside the project directory."
  exit 1
fi

# ── Load credentials from .env ───────────────────────────────────────────────

if [[ ! -f "$ENV_FILE" ]]; then
  log "ERROR: .env not found at $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ── Build a temporary MCP config for this run ────────────────────────────────
# This avoids the need to run setup-cli-mcp.sh separately.

MCP_CONFIG_FILE="$(mktemp /tmp/review-mcp-XXXXXX.json)"
trap 'rm -f "$MCP_CONFIG_FILE"' EXIT

cat > "$MCP_CONFIG_FILE" << MCPJSON
{
  "mcpServers": {
    "review-management": {
      "command": "node",
      "args": ["$DIST_JS"],
      "env": {
        "GOOGLE_CLIENT_ID": "$GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET": "$GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN": "$GOOGLE_REFRESH_TOKEN",
        "GOOGLE_ACCOUNT_ID": "$GOOGLE_ACCOUNT_ID",
        "GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON": "${GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON:-}",
        "GOOGLE_LOCATION_ID_BAKUDAN_BANDERA": "${GOOGLE_LOCATION_ID_BAKUDAN_BANDERA:-}",
        "GOOGLE_LOCATION_ID_BAKUDAN_RIM": "${GOOGLE_LOCATION_ID_BAKUDAN_RIM:-}",
        "GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK": "${GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK:-}"
      }
    }
  }
}
MCPJSON

log "MCP config written to: $MCP_CONFIG_FILE"

# ── Date range: last successful run → today ──────────────────────────────────
# On the first run (no tracker file), SINCE_DATE defaults to today so we don't
# process the entire historical backlog.
# On every subsequent run, SINCE_DATE is the date of the last successful run,
# so missed days (e.g. OAuth outage, machine asleep) are caught up automatically.

TODAY=$(date +%Y-%m-%d)
LAST_RUN_FILE="$PROJECT_DIR/logs/last-run.txt"

if [[ -f "$LAST_RUN_FILE" ]]; then
  SINCE_DATE=$(cat "$LAST_RUN_FILE")
  log "Last successful run: $SINCE_DATE — processing reviews from $SINCE_DATE through $TODAY"
else
  SINCE_DATE="$TODAY"
  log "No previous run on record — starting from today ($TODAY)"
fi

# ── Prompt for Claude ────────────────────────────────────────────────────────

PROMPT="You are a fully automated review responder running as a scheduled background job.
CRITICAL: This is a non-interactive script. DO NOT ask questions. DO NOT ask for permission.
DO NOT pause. Take every action directly and immediately.

Use the review-management MCP tools to:

STEP 1 — Call list_new_reviews with no location filter and since_date=\"$SINCE_DATE\" to get all reviews from $SINCE_DATE through today that haven't been responded to.

STEP 2 — For each NEW review rated 4 or 5 stars:
Post a response IMMEDIATELY using post_review_response. Do not ask. Just post it.
Guidelines:
- Warm, grateful tone
- Use the reviewer's first name
- Reference specific dishes or staff if mentioned
- 2-3 sentences max
- Sign off as '- The Raw Sushi team' or '- The Bakudan Ramen team' depending on location
- One 🙏 emoji only on 5-star reviews; no emoji on 4-star
- approved_by_owner is NOT needed for 4-5 star reviews

STEP 3 — For each NEW review rated 1, 2, or 3 stars:
Do NOT post a response. Instead, call save_pending_review with ALL of these fields:
- location: the location key
- review_id: the exact review ID from STEP 1
- reviewer_name: reviewer's name
- stars: numeric star rating (1, 2, or 3)
- review_date: date in YYYY-MM-DD format
- review_text: the full review text
- draft_response: a personalized, empathetic draft that acknowledges the specific complaint,
  apologizes sincerely, and invites them to contact management directly to make it right.
  Address the reviewer by first name. 3-4 sentences max.

STEP 4 — Print a one-line summary: 'Auto-posted: N | Saved to pending: M'

Remember: zero questions, zero pauses. Complete all steps autonomously."

# ── Find claude binary ───────────────────────────────────────────────────────
# When run by launchd the PATH is minimal, so we:
# 1. Source common shell profiles to pick up nvm / Homebrew / pyenv paths
# 2. Check a broad list of known install locations
# 3. Let the user override by setting CLAUDE_BIN in their environment

# Source shell profiles (safe — they're read-only)
for profile in \
  "$HOME/.zshrc" \
  "$HOME/.zprofile" \
  "$HOME/.bash_profile" \
  "$HOME/.bashrc" \
  "$HOME/.profile"; do
  # shellcheck disable=SC1090
  [[ -f "$profile" ]] && source "$profile" 2>/dev/null || true
done

CLAUDE_BIN=""
# Build candidate list: env override → common hard paths → dynamic lookup
CANDIDATES=(
  "${CLAUDE_BIN_OVERRIDE:-}"
  "/usr/local/bin/claude"
  "/opt/homebrew/bin/claude"
  "$HOME/.claude/local/claude"
  "$HOME/.local/bin/claude"
  "$HOME/.npm-global/bin/claude"
  "$HOME/.npm/bin/claude"
)

# Add npm prefix bin if npm is available
if command -v npm &>/dev/null; then
  CANDIDATES+=("$(npm config get prefix 2>/dev/null)/bin/claude")
fi

# Add PATH-based lookup after profiles are sourced
CANDIDATES+=("$(command -v claude 2>/dev/null || true)")

for candidate in "${CANDIDATES[@]}"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    CLAUDE_BIN="$candidate"
    break
  fi
done

if [[ -z "$CLAUDE_BIN" ]]; then
  log "ERROR: claude binary not found."
  log "  Tried: ${CANDIDATES[*]}"
  log ""
  log "  Fix option 1 (easiest): run  'which claude'  in your terminal, then"
  log "  add this line to the top of auto-respond.sh (before the CANDIDATES array):"
  log "    CLAUDE_BIN_OVERRIDE=/paste/path/here"
  log ""
  log "  Fix option 2: add the directory to PATH in ~/.zshrc (or ~/.bash_profile)"
  log "  then reload: source ~/.zshrc"
  exit 1
fi

log "Using claude binary: $CLAUDE_BIN"
log "Running Haiku review check..."

# ── Run Claude with the self-contained MCP config ────────────────────────────
# Disable errexit around the Claude call so we can capture the exit code
# and decide whether to advance the last-run tracker.

set +e
"$CLAUDE_BIN" \
  --model claude-haiku-4-5-20251001 \
  --mcp-config "$MCP_CONFIG_FILE" \
  --allowedTools "mcp__review-management__list_new_reviews,mcp__review-management__post_review_response,mcp__review-management__save_pending_review" \
  --dangerously-skip-permissions \
  -p "$PROMPT" \
  >> "$LOG_FILE" 2>&1
CLAUDE_EXIT=$?
set -e

# ── Advance last-run tracker only on success ─────────────────────────────────
# If Claude failed (OAuth error, network issue, etc.), we leave last-run.txt
# unchanged so the next run will retry from the same SINCE_DATE.

if [[ $CLAUDE_EXIT -eq 0 ]]; then
  echo "$TODAY" > "$LAST_RUN_FILE"
  log "Last-run tracker updated: $TODAY"
else
  log "WARNING: Claude exited with code $CLAUDE_EXIT — last-run tracker NOT updated."
  log "         Next run will retry from $SINCE_DATE."
fi

# ── Notify managers of pending 1-3★ reviews ─────────────────────────────────
# Run on every execution (not just when new reviews came in) so that
# reminders are sent on schedule even if no new reviews arrived today.

log "Running manager notifications (new reviews + overdue reminders)..."
node "$PROJECT_DIR/scripts/notify-pending.mjs" >> "$LOG_FILE" 2>&1 || \
  log "WARNING: notify-pending.mjs exited with an error (check log above)"

log "=== Review auto-responder complete (exit: $CLAUDE_EXIT) ==="
