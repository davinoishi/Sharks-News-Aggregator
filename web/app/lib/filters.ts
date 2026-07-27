/**
 * Feed filter state.
 *
 * The default time window and the "is anything filtered?" test are needed by
 * both the filter panel (whether to offer its clear control) and the feed page
 * (whether an empty result is a dead end the reader can recover from). Keeping
 * them here stops the '24h' literal from being defined twice.
 */

export interface ActiveEntity {
  slug: string;
  name: string;
}

export interface Filters {
  tags: string[];
  since: string;
  entity: ActiveEntity | null;
}

export const DEFAULT_SINCE = '24h';

export const DEFAULT_FILTERS: Filters = {
  tags: [],
  since: DEFAULT_SINCE,
  entity: null,
};

export function hasActiveFilters(filters: Filters): boolean {
  return (
    filters.tags.length > 0 ||
    filters.since !== DEFAULT_SINCE ||
    filters.entity !== null
  );
}
