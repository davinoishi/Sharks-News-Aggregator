/**
 * TypeScript types for the Sharks News Aggregator API
 */

export interface Tag {
  id: number;
  name: string;
  slug: string;
  color: string;
}

export interface Entity {
  id: number;
  name: string;
  slug: string;
  type: 'player' | 'coach' | 'team';
}

export interface StoryVariant {
  variant_id: number;
  title: string;
  url: string;
  published_at: string;
  content_type: string;
  source_name: string;
  source_category: string;
}

export interface Cluster {
  id: number;
  headline: string;
  event_type: string;
  first_seen_at: string;
  last_seen_at: string;
  source_count: number;
  click_count: number;
  tags: Tag[];
  entities: Entity[];
  // Top-ranked source URL (official→press→other), used to make the headline a
  // real link without fetching cluster detail. Absent if the cluster has no
  // variants.
  top_url?: string | null;
  /** A few sibling headlines, so a mis-merged story is visible on the card
   *  rather than hidden behind "View sources" (brief 15, SK-5). Empty for
   *  single-variant clusters. */
  preview_headlines?: string[];
  /** Clusters the matcher nearly merged this one with. Briefs 14/15 split more
   *  on purpose; this keeps a split card from being a dead end (brief 15, SK-4).
   *  Each entry carries its own top URL — there is no per-cluster page. */
  related?: { id: number; headline: string; url?: string | null }[];
  variants?: StoryVariant[];
}

export interface SiteStats {
  page_views: number;
  total_stories: number;
  total_sources: number;
}

export interface FeedResponse {
  clusters: Cluster[];
  cursor?: string | null;
  has_more: boolean;
}

export interface EntitiesResponse {
  entities: Entity[];
}

/**
 * Outlet as published by the API's public `/sources`. Deliberately narrower
 * than the admin shape — no feed URL, status, or error counts.
 */
export interface PublicSource {
  name: string;
  base_url: string;
  category: string;
}

export interface SourcesResponse {
  sources: PublicSource[];
}

export interface ClusterDetailResponse {
  cluster: Cluster;
  variants: StoryVariant[];
}
