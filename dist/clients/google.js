/**
 * Google Business Profile API Client (v4)
 *
 * Uses mybusiness.googleapis.com/v4 for reviews (the only endpoint
 * that supports reading and replying to reviews).
 *
 * Auth: OAuth 2.0 with offline access (refresh token).
 */
import fetch from "node-fetch";
// ─── Client ───────────────────────────────────────────────────────────────────
export class GoogleBusinessClient {
    cfg;
    accessToken = null;
    tokenExpiry = 0;
    // Base URLs
    accountsBase = "https://mybusinessaccountmanagement.googleapis.com/v1";
    bizInfoBase = "https://mybusinessbusinessinformation.googleapis.com/v1";
    reviewsBase = "https://mybusiness.googleapis.com/v4";
    constructor(cfg) {
        this.cfg = cfg;
    }
    // ── Auth ──────────────────────────────────────────────────────────────────
    async token() {
        if (this.accessToken && Date.now() < this.tokenExpiry) {
            return this.accessToken;
        }
        const res = await fetch("https://oauth2.googleapis.com/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: new URLSearchParams({
                client_id: this.cfg.clientId,
                client_secret: this.cfg.clientSecret,
                refresh_token: this.cfg.refreshToken,
                grant_type: "refresh_token",
            }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
            throw new Error(`OAuth refresh failed: ${data.error ?? res.status} — ${data.error_description ?? res.statusText}`);
        }
        this.accessToken = data.access_token;
        this.tokenExpiry = Date.now() + data.expires_in * 1000 - 60_000;
        return this.accessToken;
    }
    async get(url) {
        const t = await this.token();
        const res = await fetch(url, { headers: { Authorization: `Bearer ${t}` } });
        const data = await res.json();
        if (!res.ok || data.error) {
            throw new Error(`GBP API error ${res.status}: ${JSON.stringify(data.error ?? data)}`);
        }
        return data;
    }
    async put(url, body) {
        const t = await this.token();
        const res = await fetch(url, {
            method: "PUT",
            headers: {
                Authorization: `Bearer ${t}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
            throw new Error(`GBP API error ${res.status}: ${JSON.stringify(data.error ?? data)}`);
        }
        return data;
    }
    async del(url) {
        const t = await this.token();
        const res = await fetch(url, {
            method: "DELETE",
            headers: { Authorization: `Bearer ${t}` },
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(`GBP API error ${res.status}: ${JSON.stringify(data.error ?? data)}`);
        }
    }
    // ── Locations ─────────────────────────────────────────────────────────────
    async listLocations(accountId) {
        const data = await this.get(`${this.bizInfoBase}/accounts/${accountId}/locations` +
            `?readMask=name,title,websiteUri,storefrontAddress`);
        return (data.locations ?? []).map((l) => ({
            id: l.name.split("/").pop(),
            name: l.name,
            title: l.title,
            address: [
                ...(l.storefrontAddress?.addressLines ?? []),
                l.storefrontAddress?.locality,
                l.storefrontAddress?.administrativeArea,
            ]
                .filter(Boolean)
                .join(", "),
            website: l.websiteUri,
        }));
    }
    // ── Reviews ───────────────────────────────────────────────────────────────
    /** Fetch all reviews for a location (newest first, up to 50). */
    async getReviews(accountId, locationId) {
        const data = await this.get(`${this.reviewsBase}/accounts/${accountId}/locations/${locationId}/reviews` +
            `?orderBy=updateTime desc&pageSize=50`);
        return (data.reviews ?? []).map((r) => this.mapReview(r));
    }
    /** Fetch a single review by its resource name. */
    async getReview(reviewName) {
        const data = await this.get(`${this.reviewsBase}/${reviewName}`);
        return this.mapReview(data);
    }
    /** Post or update a reply on a review. */
    async postReply(accountId, locationId, reviewId, text) {
        await this.put(`${this.reviewsBase}/accounts/${accountId}/locations/${locationId}/reviews/${reviewId}/reply`, { comment: text });
    }
    /** Delete an existing reply. */
    async deleteReply(accountId, locationId, reviewId) {
        await this.del(`${this.reviewsBase}/accounts/${accountId}/locations/${locationId}/reviews/${reviewId}/reply`);
    }
    // ── Helpers ───────────────────────────────────────────────────────────────
    mapReview(r) {
        const starMap = {
            ONE: 1, TWO: 2, THREE: 3, FOUR: 4, FIVE: 5,
        };
        return {
            id: r.reviewId ?? r.name?.split("/").pop() ?? "",
            name: r.name ?? "",
            rating: starMap[r.starRating] ?? 0,
            text: r.comment ?? "",
            reviewer_name: r.reviewer?.displayName ?? "Anonymous",
            date: r.createTime ?? "",
            reply: r.reviewReply
                ? { text: r.reviewReply.comment, date: r.reviewReply.updateTime }
                : undefined,
        };
    }
}
