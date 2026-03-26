/**
 * Yelp API Client
 *
 * Handles authentication and requests to Yelp Fusion API
 */

import fetch from 'node-fetch';

export interface YelpReview {
  id: string;
  rating: number;
  text: string;
  reviewer_name: string;
  date: string;
  url: string;
}

export class YelpClient {
  private apiKey: string;
  private baseUrl = 'https://api.yelp.com/v3';

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  /**
   * Get reviews for a business
   * Note: Yelp API returns max 3 reviews in free tier
   */
  async getReviews(businessId: string): Promise<YelpReview[]> {
    const response = await fetch(`${this.baseUrl}/businesses/${businessId}/reviews`, {
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Yelp API error: ${response.status} ${response.statusText}`);
    }

    const data: any = await response.json();

    return data.reviews.map((r: any) => ({
      id: r.id,
      rating: r.rating,
      text: r.text,
      reviewer_name: r.user.name,
      date: r.time_created,
      url: r.url,
    }));
  }

  /**
   * Get a specific review
   */
  async getReview(reviewId: string): Promise<YelpReview> {
    // Note: Yelp doesn't have a direct "get review by ID" endpoint
    // This is a placeholder - in practice, you'd need to fetch business reviews
    // and filter for the specific ID
    throw new Error('Not implemented - Yelp does not support fetching individual reviews by ID');
  }

  /**
   * Post a response to a review
   * Note: This requires Yelp Partner API access (not publicly available)
   */
  async postResponse(reviewId: string, responseText: string): Promise<void> {
    // This is a placeholder for the Partner API endpoint
    // The actual endpoint is: POST /v2/businesses/{business_id}/reviews/{review_id}/reply
    // Requires special partner access

    throw new Error(
      'Yelp response posting requires Partner API access. ' +
      'Apply at: https://www.yelp.com/developers/documentation/v3/respond_to_reviews'
    );

    /*
    // When you have partner access, uncomment this:
    const response = await fetch(
      `https://api.yelp.com/v2/businesses/${businessId}/reviews/${reviewId}/reply`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text: responseText }),
      }
    );

    if (!response.ok) {
      throw new Error(`Yelp API error: ${response.status} ${response.statusText}`);
    }
    */
  }
}
