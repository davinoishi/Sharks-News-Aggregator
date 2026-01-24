/**
 * API client for Sharks News Aggregator backend
 */

import { FeedResponse, ClusterDetailResponse } from './types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export class ApiClient {
  static async getFeed(params?: {
    tags?: string;
    entities?: string;
    since?: string;
    limit?: number;
    cursor?: string;
  }): Promise<FeedResponse> {
    const searchParams = new URLSearchParams();

    if (params?.tags) searchParams.set('tags', params.tags);
    if (params?.entities) searchParams.set('entities', params.entities);
    if (params?.since) searchParams.set('since', params.since);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.cursor) searchParams.set('cursor', params.cursor);

    const url = `${API_BASE_URL}/feed?${searchParams.toString()}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch feed: ${response.statusText}`);
    }

    return response.json();
  }

  static async getCluster(id: number): Promise<ClusterDetailResponse> {
    const url = `${API_BASE_URL}/cluster/${id}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch cluster: ${response.statusText}`);
    }

    return response.json();
  }

  static async submitLink(url: string): Promise<{ status: string; message?: string }> {
    const response = await fetch(`${API_BASE_URL}/submit/link`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to submit link');
    }

    return response.json();
  }

  static async getHealth(): Promise<{ ok: boolean; timestamp: string; last_scan_at?: string }> {
    const url = `${API_BASE_URL}/health`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to fetch health: ${response.statusText}`);
    }

    return response.json();
  }
}
