/**
 * reauth.mjs — Re-authorize Google OAuth and get a fresh refresh token.
 *
 * Run this when auto-respond.sh reports "OAuth token has expired".
 *
 * Usage (in Terminal, from the review-management-mcp folder):
 *   node scripts/reauth.mjs
 *
 * It will:
 *   1. Start a temporary local web server on port 8080
 *   2. Open (or print) an authorization URL — approve it in your browser
 *   3. Automatically catch the auth code when Google redirects back
 *   4. Exchange it for a new refresh token
 *   5. Offer to patch your .env file automatically
 *
 * PREREQUISITE — add this redirect URI in Google Cloud Console ONCE:
 *   http://localhost:8080
 *   Console → APIs & Services → Credentials → your OAuth Client ID → Edit
 *   → Authorized redirect URIs → Add URI → Save
 */

import https        from "https";
import http         from "http";
import fs           from "fs";
import path         from "path";
import { execSync } from "child_process";
import { fileURLToPath } from "url";

// ─── Load credentials from .env ──────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath   = path.join(__dirname, "..", ".env");

let CLIENT_ID     = "";
let CLIENT_SECRET = "";

if (fs.existsSync(envPath)) {
  const lines = fs.readFileSync(envPath, "utf-8").split("\n");
  for (const line of lines) {
    const eqIdx = line.indexOf("=");
    if (eqIdx === -1) continue;
    const key = line.slice(0, eqIdx).trim();
    const val = line.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    if (key === "GOOGLE_CLIENT_ID")     CLIENT_ID     = val;
    if (key === "GOOGLE_CLIENT_SECRET") CLIENT_SECRET = val;
  }
}

if (!CLIENT_ID || !CLIENT_SECRET) {
  console.error("❌  Could not read GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET from .env");
  console.error(`    Looking for .env at: ${envPath}`);
  process.exit(1);
}

// ─── Config ───────────────────────────────────────────────────────────────────

const PORT         = 8080;
const REDIRECT_URI = `http://localhost:${PORT}`;
const SCOPES       = "https://www.googleapis.com/auth/business.manage";

// ─── Build the auth URL ───────────────────────────────────────────────────────

function buildAuthUrl() {
  return "https://accounts.google.com/o/oauth2/v2/auth?" + new URLSearchParams({
    client_id:     CLIENT_ID,
    redirect_uri:  REDIRECT_URI,
    response_type: "code",
    scope:         SCOPES,
    access_type:   "offline",
    prompt:        "consent",   // forces a fresh refresh token
  });
}

// ─── Exchange auth code for tokens ───────────────────────────────────────────

function exchangeCode(code) {
  return new Promise((resolve, reject) => {
    const body = Buffer.from(new URLSearchParams({
      client_id:     CLIENT_ID,
      client_secret: CLIENT_SECRET,
      redirect_uri:  REDIRECT_URI,
      code,
      grant_type: "authorization_code",
    }).toString());

    const req = https.request(
      {
        hostname: "oauth2.googleapis.com",
        path:     "/token",
        method:   "POST",
        headers:  {
          "Content-Type":   "application/x-www-form-urlencoded",
          "Content-Length": body.length,
        },
      },
      res => {
        let raw = "";
        res.on("data", c => (raw += c));
        res.on("end", () => resolve(JSON.parse(raw)));
      }
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log("\n=== Google OAuth Re-Authorization ===\n");

  // Wait for Google to redirect back with the auth code
  const code = await new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url    = new URL(req.url, `http://localhost:${PORT}`);
      const code   = url.searchParams.get("code");
      const error  = url.searchParams.get("error");

      if (error) {
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(`<h2>❌ Auth failed: ${error}</h2><p>You can close this tab.</p>`);
        server.close();
        reject(new Error(`Auth denied: ${error}`));
        return;
      }

      if (code) {
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(`
          <h2>✅ Authorization successful!</h2>
          <p>You can close this browser tab and return to Terminal.</p>
        `);
        server.close();
        resolve(code);
      }
    });

    server.listen(PORT, () => {
      const authUrl = buildAuthUrl();
      console.log("Step 1: Open this URL in your browser to sign in with Google:\n");
      console.log("  " + authUrl);
      console.log(`\nWaiting for Google to redirect to localhost:${PORT}…\n`);

      // Try to auto-open on macOS
      try {
        execSync(`open "${authUrl}"`, { stdio: "ignore" });
        console.log("(Browser should open automatically — if not, copy the URL above)\n");
      } catch {
        // ignore — user can open manually
      }
    });

    server.on("error", err => {
      if (err.code === "EADDRINUSE") {
        console.error(`\n❌  Port ${PORT} is already in use.`);
        console.error(`    Close whatever is running on port ${PORT} and try again.`);
        console.error(`    (Run: lsof -ti:${PORT} | xargs kill)`);
      } else {
        console.error("Server error:", err);
      }
      reject(err);
    });
  });

  console.log("✅  Auth code received. Exchanging for tokens…");
  const tokens = await exchangeCode(code);

  if (tokens.error) {
    console.error(`\n❌  Token exchange failed: ${tokens.error}`);
    console.error(`    ${tokens.error_description ?? ""}`);
    console.error("\n--- Did you add http://localhost:8080 to authorized redirect URIs? ---");
    console.error("    Console: https://console.cloud.google.com/apis/credentials");
    console.error("    Open your OAuth client → Edit → Authorized redirect URIs → Add URI");
    process.exit(1);
  }

  if (!tokens.refresh_token) {
    console.error("\n❌  No refresh_token in response. This usually means the app already");
    console.error("    has an approved token. Try revoking access first:");
    console.error("    https://myaccount.google.com/permissions");
    console.error("    Then run this script again.");
    process.exit(1);
  }

  console.log("\n✅  New refresh token obtained!\n");
  console.log("─────────────────────────────────────────────────────────");
  console.log(`GOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`);
  console.log("─────────────────────────────────────────────────────────\n");

  // Patch .env automatically
  let envText = fs.readFileSync(envPath, "utf-8");
  if (envText.includes("GOOGLE_REFRESH_TOKEN=")) {
    envText = envText.replace(
      /^GOOGLE_REFRESH_TOKEN=.*/m,
      `GOOGLE_REFRESH_TOKEN=${tokens.refresh_token}`
    );
  } else {
    envText += `\nGOOGLE_REFRESH_TOKEN=${tokens.refresh_token}\n`;
  }
  fs.writeFileSync(envPath, envText);
  console.log("✅  .env patched automatically with the new token.");
  console.log("    Run auto-respond.sh again — it should work now.\n");
}

main().catch(err => {
  console.error("\nUnexpected error:", err.message);
  process.exit(1);
});
