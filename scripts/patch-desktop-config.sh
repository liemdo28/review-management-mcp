#!/bin/bash
# =============================================================================
# patch-desktop-config.sh — Adds Bakudan env vars to Claude Desktop's MCP config
#
# Run once from your terminal:
#   chmod +x scripts/patch-desktop-config.sh
#   ./scripts/patch-desktop-config.sh
# =============================================================================

set -euo pipefail

CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
BACKUP="$HOME/Library/Application Support/Claude/claude_desktop_config.backup.json"

if [[ ! -f "$CONFIG" ]]; then
  echo "❌  Claude Desktop config not found at: $CONFIG"
  exit 1
fi

echo "📄  Config found: $CONFIG"
echo "💾  Backing up to: $BACKUP"
cp "$CONFIG" "$BACKUP"

# Use node to patch the JSON (safer than sed on JSON)
node << 'NODEEOF'
const fs   = require("fs");
const path = require("path");

const configPath = path.join(
  process.env.HOME,
  "Library/Application Support/Claude/claude_desktop_config.json"
);

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));

const servers = config.mcpServers ?? {};
const rm = servers["review-management"];

if (!rm) {
  console.error("❌  'review-management' MCP not found in config.");
  console.error("    Existing servers:", Object.keys(servers).join(", ") || "(none)");
  process.exit(1);
}

// Add / overwrite the Bakudan env vars
rm.env = rm.env ?? {};
rm.env["GOOGLE_LOCATION_ID_BAKUDAN_BANDERA"]   = "9390782300587134823";
rm.env["GOOGLE_LOCATION_ID_BAKUDAN_RIM"]        = "4435485907466482087";
rm.env["GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK"]  = "1599829923443837201";

// Also fix Raw Sushi ID (remove stale 'locations/' prefix if present)
if (rm.env["GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON"]?.startsWith("locations/")) {
  rm.env["GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON"] = "13520279089747024075";
  console.log("✅  Fixed Raw Sushi location ID (removed 'locations/' prefix)");
}

fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
console.log("✅  Bakudan env vars added to review-management MCP config.");
console.log("    Bandera   : 9390782300587134823");
console.log("    The Rim   : 4435485907466482087");
console.log("    Stone Oak : 1599829923443837201");
console.log("");
console.log("👉  Now quit Claude Desktop (Cmd+Q) and relaunch it.");
NODEEOF
