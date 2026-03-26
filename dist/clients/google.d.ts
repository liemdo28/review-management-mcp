/**
 * Google Business Profile API Client (v4)
 *
 * Uses mybusiness.googleapis.com/v4 for reviews (the only endpoint
 * that supports reading and replying to reviews).
 *
 * Auth: OAuth 2.0 with offline access (refresh token).
 */
export interface GBPReview {
    id: string;
    name: string;
    rating: number;
    text: string;
    reviewer_name: string;
    date: string;
    reply?: {
        text: string;
        date: string;
    };
}
export interface GBPLocation {
    id: string;
    name: string;
    title: string;
    address: string;
    website?: string;
}
interface OAuthConfig {
    clientId: string;
    clientSecret: string;
    refreshToken: string;
}
export declare class GoogleBusinessClient {
    private cfg;
    private accessToken;
    private tokenExpiry;
    private readonly accountsBase;
    private readonly bizInfoBase;
    private readonly reviewsBase;
    constructor(cfg: OAuthConfig);
    private token;
    private get;
    private put;
    private del;
    listLocations(accountId: string): Promise<GBPLocation[]>;
    /** Fetch all reviews for a location (newest first, up to 50). */
    getReviews(accountId: string, locationId: string): Promise<GBPReview[]>;
    /** Fetch a single review by its resource name. */
    getReview(reviewName: string): Promise<GBPReview>;
    /** Post or update a reply on a review. */
    postReply(accountId: string, locationId: string, reviewId: string, text: string): Promise<void>;
    /** Delete an existing reply. */
    deleteReply(accountId: string, locationId: string, reviewId: string): Promise<void>;
    private mapReview;
}
export {};
