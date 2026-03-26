/**
 * Yelp API Client
 *
 * Handles authentication and requests to Yelp Fusion API
 */
export interface YelpReview {
    id: string;
    rating: number;
    text: string;
    reviewer_name: string;
    date: string;
    url: string;
}
export declare class YelpClient {
    private apiKey;
    private baseUrl;
    constructor(apiKey: string);
    /**
     * Get reviews for a business
     * Note: Yelp API returns max 3 reviews in free tier
     */
    getReviews(businessId: string): Promise<YelpReview[]>;
    /**
     * Get a specific review
     */
    getReview(reviewId: string): Promise<YelpReview>;
    /**
     * Post a response to a review
     * Note: This requires Yelp Partner API access (not publicly available)
     */
    postResponse(reviewId: string, responseText: string): Promise<void>;
}
