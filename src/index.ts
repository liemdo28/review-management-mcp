#!/usr/bin/env node
/**
 * Review Management MCP Server
 * Fetches and responds to Google Business Profile reviews for
 * Raw Sushi Bar and Bakudan Ramen.
 */

import { Server }              from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  type Tool,
} from "@modelcontextprotocol/sdk/types.js";
import fs   from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { GoogleBusinessClient } from "./clients/google.js";
import { ResponseTracker }      from "./utils/tracker.js";

// ─── Config ───────────────────────────────────────────────────────────────────

const GOOGLE_ACCOUNT_ID = process.env.GOOGLE_ACCOUNT_ID ?? "";

// Derive project root from compiled file location: dist/index.js → project root
const __filename    = fileURLToPath(import.meta.url);
const __dirname_esm = path.dirname(__filename);
const PROJECT_ROOT  = path.dirname(__dirname_esm);
const PENDING_JSON  = path.join(PROJECT_ROOT, "logs", "pending-reviews.json");
const PENDING_MD    = path.join(PROJECT_ROOT, "logs", "pending-reviews.md");

/** Every location we manage. Add more entries as you find the IDs. */
const LOCATIONS: Array<{ key: string; name: string; locationId: string }> = [
  {
    key:        "raw-sushi-stockton",
    name:       "Raw Sushi Bistro (Stockton)",
    locationId: process.env.GOOGLE_LOCATION_ID_RAW_SUSHI_STOCKTON ?? "",
  },
  // Bakudan Ramen — 3 San Antonio locations (confirmed 2026-02-18 via address lookup)
  { key: "bakudan-bandera",    name: "Bakudan Ramen (Bandera)",    locationId: process.env.GOOGLE_LOCATION_ID_BAKUDAN_BANDERA    ?? "" },
  { key: "bakudan-rim",        name: "Bakudan Ramen (The Rim)",    locationId: process.env.GOOGLE_LOCATION_ID_BAKUDAN_RIM        ?? "" },
  { key: "bakudan-stone-oak",  name: "Bakudan Ramen (Stone Oak)",  locationId: process.env.GOOGLE_LOCATION_ID_BAKUDAN_STONE_OAK  ?? "" },
  // Uncomment when found:
  // { key: "raw-sushi-modesto", name: "Raw Sushi (Modesto)", locationId: process.env.GOOGLE_LOCATION_ID_RAW_SUSHI_MODESTO ?? "" },
].filter(l => l.locationId !== "");   // skip unconfigured locations

// ─── Server ───────────────────────────────────────────────────────────────────

class ReviewServer {
  private server:  Server;
  private google:  GoogleBusinessClient;
  private tracker: ResponseTracker;

  constructor() {
    this.server = new Server(
      { name: "review-management-mcp", version: "1.0.0" },
      { capabilities: { tools: {} } }
    );

    this.google = new GoogleBusinessClient({
      clientId:     process.env.GOOGLE_CLIENT_ID     ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
      refreshToken: process.env.GOOGLE_REFRESH_TOKEN ?? "",
    });

    this.tracker = new ResponseTracker();
    this.wire();
  }

  // ── Tool definitions ──────────────────────────────────────────────────────

  private tools(): Tool[] {
    const locationEnum = LOCATIONS.map(l => l.key);
    const locationDesc = LOCATIONS.map(l => `${l.key} = ${l.name}`).join(", ");

    return [
      {
        name: "list_new_reviews",
        description:
          "Fetch reviews that have not been responded to yet across all configured " +
          "restaurant locations. Returns reviewer name, star rating, text, date, " +
          "and a unique review ID to use when posting a response.",
        inputSchema: {
          type: "object",
          properties: {
            location: {
              type: "string",
              enum: locationEnum.length ? locationEnum : ["raw-sushi-stockton"],
              description: `Filter to one location (${locationDesc}). Omit for all.`,
            },
            since_date: {
              type: "string",
              description:
                "Only return reviews on or after this date (YYYY-MM-DD). " +
                "Use to skip historical backlog and only surface new reviews.",
            },
          },
        },
        annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
      },
      {
        name: "list_all_reviews",
        description:
          "List all recent reviews (responded and unresponded) with optional filters.",
        inputSchema: {
          type: "object",
          properties: {
            location: {
              type: "string",
              enum: locationEnum.length ? locationEnum : ["raw-sushi-stockton"],
              description: `Location filter (${locationDesc}). Omit for all.`,
            },
            min_stars: { type: "number", minimum: 1, maximum: 5 },
            max_stars: { type: "number", minimum: 1, maximum: 5 },
            unanswered_only: { type: "boolean", default: false },
            limit: { type: "number", default: 20 },
          },
        },
        annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
      },
      {
        name: "post_review_response",
        description:
          "Post a response to a review. For 1-3 star reviews you MUST set " +
          "approved_by_owner=true as a safety check — always show the draft " +
          "to the owner first and wait for explicit approval.",
        inputSchema: {
          type: "object",
          required: ["location", "review_id", "response_text"],
          properties: {
            location: {
              type: "string",
              enum: locationEnum.length ? locationEnum : ["raw-sushi-stockton"],
              description: `Which restaurant (${locationDesc})`,
            },
            review_id: {
              type: "string",
              description: "Review ID from list_new_reviews or list_all_reviews",
            },
            response_text: {
              type: "string",
              description: "The response text to post",
            },
            approved_by_owner: {
              type: "boolean",
              default: false,
              description: "Must be true for 1-3 star reviews",
            },
          },
        },
        annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false },
      },
      {
        name: "save_pending_review",
        description:
          "Save a 1-3★ review to the pending queue for manager email notification " +
          "and follow-up tracking. Use this for ALL negative reviews instead of the Write tool.",
        inputSchema: {
          type: "object",
          required: ["location", "review_id", "reviewer_name", "stars", "review_date", "review_text", "draft_response"],
          properties: {
            location: {
              type: "string",
              enum: locationEnum.length ? locationEnum : ["raw-sushi-stockton"],
              description: locationDesc,
            },
            review_id:       { type: "string", description: "Review ID from list_new_reviews" },
            reviewer_name:   { type: "string" },
            stars:           { type: "number", minimum: 1, maximum: 3 },
            review_date:     { type: "string", description: "YYYY-MM-DD" },
            review_text:     { type: "string" },
            draft_response:  { type: "string", description: "Empathetic draft response for manager to review" },
          },
        },
        annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true },
      },
      {
        name: "get_response_history",
        description: "View history of all responses posted through this system.",
        inputSchema: {
          type: "object",
          properties: {
            since_date: { type: "string", description: "ISO date (e.g. 2026-01-01)" },
            limit:      { type: "number", default: 50 },
          },
        },
        annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true },
      },
    ];
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  private wire() {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: this.tools(),
    }));

    this.server.setRequestHandler(CallToolRequestSchema, async (req) => {
      const { name, arguments: args = {} } = req.params;
      try {
        switch (name) {
          case "list_new_reviews":      return await this.listNewReviews(args);
          case "list_all_reviews":      return await this.listAllReviews(args);
          case "post_review_response":  return await this.postResponse(args);
          case "save_pending_review":   return await this.savePendingReview(args);
          case "get_response_history":  return await this.getHistory(args);
          default: throw new Error(`Unknown tool: ${name}`);
        }
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    });
  }

  // ── Tool implementations ──────────────────────────────────────────────────

  private async listNewReviews(args: any) {
    const targets = this.resolveLocations(args.location);
    const sinceDate: string | null = args.since_date ?? null;
    const lines: string[] = [];
    let totalNew = 0;

    for (const loc of targets) {
      const reviews = await this.google.getReviews(GOOGLE_ACCOUNT_ID, loc.locationId);
      const fresh = reviews.filter(r =>
        !this.tracker.hasResponded(r.id) &&   // not already tracked locally
        !r.reply &&                            // not already replied on Google
        (!sinceDate || r.date.slice(0, 10) >= sinceDate)  // within date window
      );

      if (fresh.length === 0) continue;
      totalNew += fresh.length;

      lines.push(`\n## ${loc.name}  (${fresh.length} new)\n`);
      for (const r of fresh) {
        lines.push(
          `**Review ID**: ${r.id}\n` +
          `**Rating**: ${"⭐".repeat(r.rating)}\n` +
          `**Reviewer**: ${r.reviewer_name}\n` +
          `**Date**: ${r.date.slice(0, 10)}\n` +
          `**Text**: ${r.text || "(no text)"}\n`
        );
      }
    }

    const header = totalNew === 0
      ? "✅ No new reviews — all caught up!"
      : `Found **${totalNew}** new review(s) awaiting a response:\n`;

    return { content: [{ type: "text", text: header + lines.join("\n---\n") }] };
  }

  private async listAllReviews(args: any) {
    const targets = this.resolveLocations(args.location);
    const minStars: number = args.min_stars ?? 1;
    const maxStars: number = args.max_stars ?? 5;
    const unansweredOnly: boolean = args.unanswered_only ?? false;
    const limit: number = args.limit ?? 20;

    const lines: string[] = [];
    let count = 0;

    for (const loc of targets) {
      const reviews = await this.google.getReviews(GOOGLE_ACCOUNT_ID, loc.locationId);

      const filtered = reviews
        .filter(r => r.rating >= minStars && r.rating <= maxStars)
        .filter(r => !unansweredOnly || !this.tracker.hasResponded(r.id))
        .slice(0, limit - count);

      if (filtered.length === 0) continue;
      count += filtered.length;
      lines.push(`\n## ${loc.name}\n`);

      for (const r of filtered) {
        const replied = r.reply ? "✅ replied" : "⚠️ no reply";
        lines.push(
          `**Review ID**: ${r.id} [${replied}]\n` +
          `**Rating**: ${"⭐".repeat(r.rating)}  |  **Date**: ${r.date.slice(0, 10)}\n` +
          `**Reviewer**: ${r.reviewer_name}\n` +
          `**Text**: ${r.text || "(no text)"}\n` +
          (r.reply ? `**Your reply**: ${r.reply.text}\n` : "")
        );
      }

      if (count >= limit) break;
    }

    return {
      content: [{
        type: "text",
        text: count === 0
          ? "No reviews match the filters."
          : `Showing ${count} review(s):\n` + lines.join("\n---\n"),
      }],
    };
  }

  private async postResponse(args: any) {
    const { location, review_id, response_text, approved_by_owner } = args;

    const loc = LOCATIONS.find(l => l.key === location);
    if (!loc) throw new Error(`Unknown location key: ${location}`);

    // Fetch the review to check star rating
    const reviews = await this.google.getReviews(GOOGLE_ACCOUNT_ID, loc.locationId);
    const review = reviews.find(r => r.id === review_id);
    if (!review) throw new Error(`Review ${review_id} not found in ${loc.name}`);

    // Safety gate for negative reviews
    if (review.rating <= 3 && !approved_by_owner) {
      return {
        content: [{
          type: "text",
          text:
            `⚠️ **Owner approval required** — this is a ${review.rating}-star review.\n\n` +
            `**Draft response:**\n${response_text}\n\n` +
            `To post it, call this tool again with \`approved_by_owner: true\`.`,
        }],
      };
    }

    await this.google.postReply(GOOGLE_ACCOUNT_ID, loc.locationId, review_id, response_text);
    this.tracker.recordResponse(review_id, response_text, !!approved_by_owner, loc.name);

    return {
      content: [{
        type: "text",
        text:
          `✅ Response posted to **${loc.name}**\n\n` +
          `**Review**: ${"⭐".repeat(review.rating)} by ${review.reviewer_name}\n` +
          `**Response**: ${response_text}\n` +
          (approved_by_owner ? "_Manually approved by owner._" : "_Auto-posted (4-5 star)._"),
      }],
    };
  }

  private async savePendingReview(args: any) {
    const { location, review_id, reviewer_name, stars, review_date, review_text, draft_response } = args;
    const loc = LOCATIONS.find(l => l.key === location);
    if (!loc) throw new Error(`Unknown location: ${location}`);

    // Load or initialise the pending queue
    let store: { pending: any[]; last_updated: string } = { pending: [], last_updated: "" };
    if (fs.existsSync(PENDING_JSON)) {
      try { store = JSON.parse(fs.readFileSync(PENDING_JSON, "utf-8")); } catch { /* ignore */ }
    }

    // Idempotent — skip if already queued
    if (store.pending.find((r: any) => r.review_id === review_id)) {
      return { content: [{ type: "text", text: `Already queued: ${reviewer_name} (${stars}★) at ${loc.name}` }] };
    }

    const entry = {
      review_id,
      location_key:      location,
      location_name:     loc.name,
      reviewer_name,
      stars,
      review_date,
      review_text,
      draft_response,
      added_at:          new Date().toISOString(),
      first_notified_at: null as string | null,
      last_reminded_at:  null as string | null,
      reminder_count:    0,
      resolved_at:       null as string | null,
    };

    store.pending.push(entry);
    store.last_updated = new Date().toISOString();

    fs.mkdirSync(path.join(PROJECT_ROOT, "logs"), { recursive: true });
    fs.writeFileSync(PENDING_JSON, JSON.stringify(store, null, 2));

    // Also append to the human-readable markdown file
    const stars_str = "⭐".repeat(stars);
    const mdLine =
      `\n## ${loc.name} — ${reviewer_name} ${stars_str} — ${review_date}\n` +
      `**Review:** ${review_text}\n` +
      `**Draft response:** ${draft_response}\n\n---\n`;
    if (fs.existsSync(PENDING_MD)) {
      fs.appendFileSync(PENDING_MD, mdLine);
    }

    return {
      content: [{ type: "text", text: `✅ Queued for manager notification: ${reviewer_name} (${stars}★) at ${loc.name}` }],
    };
  }

  private async getHistory(args: any) {
    const history = this.tracker.getHistory(args.since_date, args.limit ?? 50);
    if (history.length === 0) {
      return { content: [{ type: "text", text: "No response history yet." }] };
    }

    const lines = history.map(h =>
      `**${h.restaurant}** | ${h.timestamp.slice(0, 10)} | ` +
      `${h.approved_by_owner ? "👤 owner approved" : "🤖 auto-posted"}\n` +
      `Review ID: ${h.review_id}\n` +
      `Response: ${h.response_text.slice(0, 120)}${h.response_text.length > 120 ? "…" : ""}`
    );

    return {
      content: [{
        type: "text",
        text: `Response history (${history.length} entries):\n\n` + lines.join("\n---\n"),
      }],
    };
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  private resolveLocations(key?: string) {
    if (!key) return LOCATIONS;
    const loc = LOCATIONS.find(l => l.key === key);
    if (!loc) throw new Error(`Unknown location key: ${key}`);
    return [loc];
  }

  // ── Start ─────────────────────────────────────────────────────────────────

  async run() {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error("Review Management MCP Server started.");
  }
}

new ReviewServer().run().catch(err => {
  console.error("Fatal:", err);
  process.exit(1);
});
