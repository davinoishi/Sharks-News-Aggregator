'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiClient } from '../api-client';
import { Entity } from '../types';
import { ActiveEntity, DEFAULT_SINCE, hasActiveFilters } from '../lib/filters';

export type { ActiveEntity };

interface FilterBarProps {
  selectedTags: string[];
  since: string;
  entity: ActiveEntity | null;
  /**
   * Players and coaches most mentioned in the current window, ranked by the
   * API and rendered server-side (SEO-2). Empty is fine — the search input
   * still works, it just has nothing to suggest.
   */
  suggestedEntities?: Entity[];
  onTagsChange: (tags: string[]) => void;
  onSinceChange: (since: string) => void;
  onEntityChange: (entity: ActiveEntity | null) => void;
}

const TAG_OPTIONS = [
  { value: 'rumors', label: 'Rumors' },
  { value: 'trade', label: 'Trade' },
  { value: 'injury', label: 'Injury' },
  { value: 'lineup', label: 'Lineup' },
  { value: 'signing', label: 'Signing' },
  { value: 'waiver', label: 'Waiver' },
  { value: 'game', label: 'Game' },
  { value: 'barracuda', label: 'Barracuda' },
];

const TIME_OPTIONS = [
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
];

const focusRing =
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-1 focus-visible:ring-offset-surface';

export function FilterBar({
  selectedTags,
  since,
  entity,
  suggestedEntities = [],
  onTagsChange,
  onSinceChange,
  onEntityChange,
}: FilterBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Entity[]>([]);
  const [open, setOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Debounced entity search.
  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(async () => {
      try {
        const res = await ApiClient.searchEntities(query.trim());
        setResults(res.entities);
      } catch (err) {
        console.error('Entity search failed:', err);
        setResults([]);
      }
    }, 200);
    return () => clearTimeout(handle);
  }, [query, open]);

  // Close the dropdown when clicking outside the picker.
  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const handleTagToggle = (tag: string) => {
    const newTags = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    onTagsChange(newTags);
  };

  const selectEntity = (e: Entity) => {
    onEntityChange({ slug: e.slug, name: e.name });
    setQuery('');
    setOpen(false);
  };

  const filtersActive = hasActiveFilters({ tags: selectedTags, since, entity });
  const activeCount =
    selectedTags.length + (entity ? 1 : 0) + (since !== DEFAULT_SINCE ? 1 : 0);

  return (
    <div className="bg-surface border border-edge rounded-lg p-4 mb-6">
      {/* On a phone the open panel filled most of the first screen, so the feed
          began below the fold — the opposite of catching up in a minute. It
          collapses here and stays open from `sm` up, where there is room.
          Rendering the panel with `hidden sm:block` means the server output is
          already correct for both: no hydration branch, no desktop flash. */}
      <button
        type="button"
        onClick={() => setPanelOpen((v) => !v)}
        aria-expanded={panelOpen}
        aria-controls="filter-panel"
        className={`tap-44 sm:hidden -m-1 flex w-[calc(100%+0.5rem)] items-center justify-between rounded-md p-1 text-ui text-content ${focusRing}`}
      >
        <span className="flex items-center gap-2">
          Filters
          {activeCount > 0 && (
            <span className="rounded-full bg-action px-2 py-0.5 text-chip text-on-action tabular-nums">
              {activeCount}
              <span className="sr-only"> active</span>
            </span>
          )}
        </span>
        <svg
          className={`h-4 w-4 text-content-muted transition-transform ${panelOpen ? 'rotate-180' : ''}`}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      <div id="filter-panel" className={panelOpen ? 'mt-4 sm:mt-0' : 'hidden sm:block'}>
      <div className="mb-5" role="group" aria-labelledby="filter-tags-label">
        <p id="filter-tags-label" className="text-label uppercase text-content-muted mb-2.5">
          Filter by tags:
        </p>
        <div className="flex flex-wrap gap-x-2 gap-y-3">
          {TAG_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => handleTagToggle(option.value)}
              aria-pressed={selectedTags.includes(option.value)}
              className={`tap-44 px-3 py-1.5 rounded-full text-ui transition-colors ${focusRing} ${
                selectedTags.includes(option.value)
                  ? 'bg-action text-on-action ring-1 ring-inset ring-action'
                  : 'bg-control text-control-fg ring-1 ring-inset ring-control-edge hover:bg-control-hover'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-5" role="group" aria-labelledby="filter-player-label">
        <p id="filter-player-label" className="text-label uppercase text-content-muted mb-2.5">
          Filter by player:
        </p>
        {entity ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 pl-3 pr-1 py-1.5 rounded-full text-ui bg-action text-on-action">
              {entity.name}
              <button
                type="button"
                onClick={() => onEntityChange(null)}
                aria-label={`Clear ${entity.name} filter`}
                className={`tap-44 ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full hover:bg-on-action/20 ${focusRing}`}
              >
                <span aria-hidden="true">×</span>
              </button>
            </span>
          </div>
        ) : (
          <>
            <div className="relative max-w-xs" ref={pickerRef}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setOpen(true)}
                placeholder="Search players…"
                aria-label="Search players to filter by"
                className={`w-full min-h-[44px] px-3 py-2 text-ui font-normal border border-edge-strong rounded-lg ${focusRing}`}
              />
              {open && results.length > 0 && (
                <ul className="absolute z-10 mt-1 w-full max-h-60 overflow-auto bg-surface border border-edge rounded-lg shadow-md">
                  {results.map((e) => (
                    <li key={e.id}>
                      <button
                        type="button"
                        onClick={() => selectEntity(e)}
                        className="w-full min-h-[44px] text-left px-3 py-2 text-ui text-content-secondary hover:bg-surface-sunken"
                      >
                        {e.name}
                        <span className="ml-2 text-chip uppercase text-content-muted">{e.type}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Who is actually in the news, ranked by story count and rendered
                on the server (SEO-2). This replaces an empty text box as the
                resting state: a reader who doesn't already have a name in mind
                now has somewhere to start, and the names are in the HTML. */}
            {suggestedEntities.length > 0 && (
              <div className="mt-3">
                <p
                  id="suggested-players-label"
                  className="text-meta text-content-muted mb-2"
                >
                  In the news:
                </p>
                <div
                  className="flex flex-wrap gap-x-2 gap-y-3"
                  role="group"
                  aria-labelledby="suggested-players-label"
                >
                  {suggestedEntities.map((e) => (
                    <button
                      key={e.id}
                      type="button"
                      onClick={() => selectEntity(e)}
                      title={`Filter by ${e.name}`}
                      className={`tap-40 text-meta font-medium leading-4 px-2.5 py-1.5 rounded-full bg-control text-control-fg ring-1 ring-inset ring-control-edge hover:bg-control-hover transition-colors ${focusRing}`}
                    >
                      {e.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div role="group" aria-labelledby="filter-time-label">
        <p id="filter-time-label" className="text-label uppercase text-content-muted mb-2.5">
          Time range:
        </p>
        <div className="flex flex-wrap gap-x-2 gap-y-3">
          {TIME_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => onSinceChange(option.value)}
              aria-pressed={since === option.value}
              className={`tap-44 px-3 py-1.5 rounded-full text-ui transition-colors ${focusRing} ${
                since === option.value
                  ? 'bg-action text-on-action ring-1 ring-inset ring-action'
                  : 'bg-control text-control-fg ring-1 ring-inset ring-control-edge hover:bg-control-hover'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {filtersActive && (
        <div className="mt-4 pt-4 border-t border-edge">
          <button
            onClick={() => {
              onTagsChange([]);
              onSinceChange(DEFAULT_SINCE);
              onEntityChange(null);
            }}
            className={`tap-44 inline-flex items-center text-ui text-action hover:text-action-hover rounded-md ${focusRing}`}
          >
            Clear all filters
          </button>
        </div>
      )}
      </div>
    </div>
  );
}
