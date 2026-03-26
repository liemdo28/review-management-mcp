/**
 * Response Tracker
 *
 * Tracks which reviews have been responded to and maintains history
 */
import fs from 'fs';
import path from 'path';
export class ResponseTracker {
    trackerFile;
    responses;
    constructor(trackerFile) {
        this.trackerFile = trackerFile || path.join(process.cwd(), 'response-history.json');
        this.responses = new Map();
        this.load();
    }
    /**
     * Load response history from file
     */
    load() {
        try {
            if (fs.existsSync(this.trackerFile)) {
                const data = JSON.parse(fs.readFileSync(this.trackerFile, 'utf-8'));
                this.responses = new Map(data.responses.map((r) => [r.review_id, r]));
            }
        }
        catch (error) {
            console.error('Error loading response history:', error);
        }
    }
    /**
     * Save response history to file
     */
    save() {
        try {
            const data = {
                responses: Array.from(this.responses.values()),
                last_updated: new Date().toISOString(),
            };
            fs.writeFileSync(this.trackerFile, JSON.stringify(data, null, 2));
        }
        catch (error) {
            console.error('Error saving response history:', error);
        }
    }
    /**
     * Check if a review has been responded to
     */
    hasResponded(reviewId) {
        return this.responses.has(reviewId);
    }
    /**
     * Record a response
     */
    recordResponse(reviewId, responseText, approvedByOwner, restaurant) {
        const record = {
            review_id: reviewId,
            restaurant,
            response_text: responseText,
            timestamp: new Date().toISOString(),
            approved_by_owner: approvedByOwner,
        };
        this.responses.set(reviewId, record);
        this.save();
    }
    /**
     * Get response history
     */
    getHistory(sinceDate, limit) {
        let records = Array.from(this.responses.values());
        // Filter by date if provided
        if (sinceDate) {
            const cutoff = new Date(sinceDate);
            records = records.filter(r => new Date(r.timestamp) >= cutoff);
        }
        // Sort by timestamp descending (newest first)
        records.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        // Apply limit if provided
        if (limit) {
            records = records.slice(0, limit);
        }
        return records;
    }
    /**
     * Get statistics
     */
    getStats() {
        const records = Array.from(this.responses.values());
        return {
            total_responses: records.length,
            auto_posted: records.filter(r => !r.approved_by_owner).length,
            manually_approved: records.filter(r => r.approved_by_owner).length,
        };
    }
}
