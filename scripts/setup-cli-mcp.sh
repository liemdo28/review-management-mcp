#!/bin/bash
# =============================================================================
# setup-cli-mcp.sh — Register review-management MCP with the Claude CLI
#
# Run this ONCE after building the project. It adds the MCP server to
# Claude's global config so that auto-respond.sh (and any CLI session)
# can call the review-management tools.
#
# Usage:
#   chmod +x scripts/setup-cli-mcp.sh
#   ./scripts/setup-cli-mcp.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_JS="$PROJECT_DIR/dist/index.js"
ENV_FILE="$PROJECT_DIR/.env"

# ── Pre-flight checks ────────────────────────────────────────────────────────

if [[ ! -f "$DIST_JS" ]]; then
  echo "❌  dist/index.js not found at: $DIST_JS"
  echo "    Run 'npm run build' inside the project directory first, then re-run this script."
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌  .env not found at: $ENV_FILE"
  exit 1
fi

# Find the claude binary
CLAUDE_BIN=""
for candidate in \
  "/usr/local/bin/claude" \
  "$HOME/.claude/local/claude" \
  "$(which claude 2>/dev/null || true)"; do
  if [[ -x "$candidate" ]]; then
    CLAUDE_BIN="$candidate"
    break
  fi
done

if [[ -z "$CLAUDE_BIN" ]]; then
  echo "❌  claude binary not found. Make sure Claude Code is installed."
  exit 1
fi

# ── Load credentials from .env ───────────────────────────────────────────────

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ── Remove any existing registration first (idempotent) ──────────────────────

if "$CLAUDE_BIN" mcp list 2>/dev/null | grep -q "review-management"; then
  echo "⚠️  Existing review-management MCP found — removing it before re-registering..."
  "$CLAUDE_BIN" mcp remove review-management -s global 2>/dev/null || true
fi

# ── Register globally ────────────────────────────────────────────────────────

echo "Registering review-management MCP (global scope)..."
echo "  Server: node $DIST_JS"
echo ""

"$CLAUDE_BIN" mcp add review-management \
  -s global \
  -e "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
  -e "GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET" \
  -e "GOOGLE_REFRESH_TOKEN=$GOOGLE_REFRESH_TOKEN" \
  -e "GOOGLE_ACCOUNT_ID=$GOOGLE_ACCOUNT_ID" \
  -e "GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON=$GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON" \
  -e "GOOGLE_LOCATION_ID_BAKUDAN_BANDERA=${GOOGLE_LOCATION_ID_BAKUDAN_BANDERA:-}" \
  -e "GOOGLE_LOCATION_ID_BAKUDAN_RIM=${GOOGLE_LOCATION_ID_BAKUDAN_RIM:-}" \
  -e "GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK=${GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK:-}" \
  -- node "$DIST_JS"

echo ""
echo "✅  review-management MCP registered globally."
echo ""
echo "Verify with:"
echo "  $CLAUDE_BIN mcp list"
echo ""
echo "Quick smoke test (should list reviews or say 'all caught up'):"
echo "  $CLAUDE_BIN --model claude-haiku-4-5-20251001 \\"
echo "    --allowedTools 'mcp__review-management__list_new_reviews' \\"
echo "    -p 'List any new reviews for all locations.'"
echo ""
echo "Now run auto-respond.sh to test the full scheduled flow:"
echo "  $SCRIPT_DIR/auto-respond.sh"
