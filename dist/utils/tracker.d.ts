/**
 * Response Tracker
 *
 * Tracks which reviews have been responded to and maintains history
 */
interface ResponseRecord {
    review_id: string;
    restaurant: string;
    response_text: string;
    timestamp: string;
    approved_by_owner: boolean;
}
export declare class ResponseTracker {
    private trackerFile;
    private responses;
    constructor(trackerFile?: string);
    /**
     * Load response history from file
     */
    private load;
    /**
     * Save response history to file
     */
    private save;
    /**
     * Check if a review has been responded to
     */
    hasResponded(reviewId: string): boolean;
    /**
     * Record a response
     */
    recordResponse(reviewId: string, responseText: string, approvedByOwner: boolean, restaurant: string): void;
    /**
     * Get response history
     */
    getHistory(sinceDate?: string, limit?: number): ResponseRecord[];
    /**
     * Get statistics
     */
    getStats(): {
        total_responses: number;
        auto_posted: number;
        manually_approved: number;
    };
}
export {};
