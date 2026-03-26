/**
 * Test script — run this on your local machine to verify
 * credentials and fetch live reviews.
 *
 * Usage:
 *   node scripts/test-connection.mjs
 */

import https from "https";

const CLIENT_ID = process.env.GOOGLE_CLIENT_ID || "";
const CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET || "";
const REFRESH_TOKEN = process.env.GOOGLE_REFRESH_TOKEN || "";

const ACCOUNT_ID    = "";
const LOCATIONS     = [
  { id: "13520279089747024075", name: "Raw Sushi Bistro (Stockton)" },
  // Add more as you find them:
  // { id: "TBD", name: "Raw Sushi Modesto" },
  // { id: "TBD", name: "Bakudan Stone Oak" },
];

// ─── helpers ────────────────────────────────────────────────

function post(hostname, path, body) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(body);
    const req = https.request(
      { hostname, path, method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded",
                   "Content-Length": data.length } },
      res => {
        let raw = "";
        res.on("data", c => (raw += c));
        res.on("end", () => resolve(JSON.parse(raw)));
      }
    );
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function get(hostname, path, token) {
  return new Promise((resolve, reject) => {
    const req = https.request(
      { hostname, path, method: "GET",
        headers: { Authorization: `Bearer ${token}` } },
      res => {
        let raw = "";
        res.on("data", c => (raw += c));
        res.on("end", () => resolve(JSON.parse(raw)));
      }
    );
    req.on("error", reject);
    req.end();
  });
}

// ─── main ────────────────────────────────────────────────────

async function main() {
  console.log("=== Google Business Profile — Connection Test ===\n");

  // 1. Exchange refresh token for a fresh access token
  console.log("1. Refreshing access token…");
  const tokenRes = await post("oauth2.googleapis.com", "/token",
    new URLSearchParams({
      client_id:     CLIENT_ID,
      client_secret: CLIENT_SECRET,
      refresh_token: REFRESH_TOKEN,
      grant_type:    "refresh_token",
    }).toString()
  );

  if (tokenRes.error) {
    console.error("❌  Token refresh failed:", tokenRes.error, tokenRes.error_description);
    process.exit(1);
  }
  const token = tokenRes.access_token;
  console.log("✅  Access token obtained\n");

  // 2. Verify account is visible
  console.log("2. Checking account access…");
  const accounts = await get(
    "mybusinessaccountmanagement.googleapis.com",
    "/v1/accounts",
    token
  );
  if (accounts.error) {
    console.error("❌  Account fetch failed:", JSON.stringify(accounts.error, null, 2));
    process.exit(1);
  }
  console.log(`✅  Account found: ${accounts.accounts?.[0]?.accountName}\n`);

  // 3. List ALL locations visible under this account
  console.log("3. Listing all locations on this account…");
  const locList = await get(
    "mybusinessbusinessinformation.googleapis.com",
    `/v1/accounts/${ACCOUNT_ID}/locations?readMask=name,title,storefrontAddress`,
    token
  );
  if (locList.error) {
    console.warn("⚠️  Location list failed:", JSON.stringify(locList.error, null, 2));
    console.warn("    (continuing with hard-coded locations)\n");
  } else {
    const locs = locList.locations || [];
    console.log(`✅  Found ${locs.length} location(s) on your account:\n`);
    locs.forEach((l, i) => {
      const id = l.name?.split("/").pop() ?? "unknown";
      const sa = l.storefrontAddress;
      const street = (sa?.addressLines ?? []).join(", ");
      const city   = sa?.locality ?? "";
      const state  = sa?.administrativeArea ?? "";
      const full   = [street, city, state].filter(Boolean).join(", ");
      console.log(`  [${i + 1}] ${l.title ?? "(no title)"}`);
      console.log(`       ID  : ${id}`);
      if (full) console.log(`       Addr: ${full}`);
    });
    console.log();
  }

  // 4. Fetch reviews for each location
  for (const loc of LOCATIONS) {
    console.log(`4. Fetching reviews for ${loc.name}…`);
    const reviews = await get(
      "mybusiness.googleapis.com",
      `/v4/accounts/${ACCOUNT_ID}/locations/${loc.id}/reviews`,
      token
    );

    if (reviews.error) {
      console.error(`❌  Reviews fetch failed:`, JSON.stringify(reviews.error, null, 2));
      continue;
    }

    const list = reviews.reviews || [];
    console.log(`✅  Found ${list.length} review(s)\n`);

    list.slice(0, 3).forEach((r, i) => {
      const stars = "⭐".repeat(
        { ONE:1, TWO:2, THREE:3, FOUR:4, FIVE:5 }[r.starRating] ?? 0
      );
      const hasReply = r.reviewReply ? "✅ replied" : "⚠️  no reply yet";
      console.log(
        `  #${i + 1}  ${stars}  ${r.reviewer?.displayName ?? "Anonymous"}` +
        `  (${r.createTime?.slice(0, 10)})  [${hasReply}]`
      );
      if (r.comment) console.log(`       "${r.comment.slice(0, 80)}…"`);
    });
    console.log();
  }

  console.log("=== Test complete ✅ ===");
  console.log("\nIf you see reviews above, your MCP server is ready to configure.");
  console.log("Next step: run  npm install && npm run build  inside review-management-mcp/");
}

main().catch(err => {
  console.error("Unexpected error:", err);
  process.exit(1);
});
