'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiClient } from '../api-client';
import { Entity } from '../types';

export interface ActiveEntity {
  slug: string;
  name: string;
}

interface FilterBarProps {
  selectedTags: string[];
  since: string;
  entity: ActiveEntity | null;
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
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-[#006D75] focus-visible:ring-offset-1';

export function FilterBar({
  selectedTags,
  since,
  entity,
  onTagsChange,
  onSinceChange,
  onEntityChange,
}: FilterBarProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Entity[]>([]);
  const [open, setOpen] = useState(false);
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

  const hasActiveFilters = selectedTags.length > 0 || since !== '24h' || entity !== null;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
      <div className="mb-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Filter by tags:</h3>
        <div className="flex flex-wrap gap-2">
          {TAG_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => handleTagToggle(option.value)}
              aria-pressed={selectedTags.includes(option.value)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${focusRing} ${
                selectedTags.includes(option.value)
                  ? 'bg-[#006D75] text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Filter by player:</h3>
        {entity ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full text-sm bg-[#006D75] text-white">
              {entity.name}
              <button
                type="button"
                onClick={() => onEntityChange(null)}
                aria-label={`Clear ${entity.name} filter`}
                className={`ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full hover:bg-white/20 ${focusRing}`}
              >
                <span aria-hidden="true">×</span>
              </button>
            </span>
          </div>
        ) : (
          <div className="relative max-w-xs" ref={pickerRef}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setOpen(true)}
              placeholder="Search players…"
              aria-label="Search players to filter by"
              className={`w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg ${focusRing}`}
            />
            {open && results.length > 0 && (
              <ul className="absolute z-10 mt-1 w-full max-h-60 overflow-auto bg-white border border-gray-200 rounded-lg shadow-lg">
                {results.map((e) => (
                  <li key={e.id}>
                    <button
                      type="button"
                      onClick={() => selectEntity(e)}
                      className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                    >
                      {e.name}
                      <span className="ml-2 text-xs text-gray-400 capitalize">{e.type}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div>
        <h3 className="text-sm font-medium text-gray-700 mb-2">Time range:</h3>
        <div className="flex flex-wrap gap-2">
          {TIME_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => onSinceChange(option.value)}
              aria-pressed={since === option.value}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${focusRing} ${
                since === option.value
                  ? 'bg-[#006D75] text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {hasActiveFilters && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <button
            onClick={() => {
              onTagsChange([]);
              onSinceChange('24h');
              onEntityChange(null);
            }}
            className={`text-sm text-[#006D75] hover:text-[#005a61] rounded ${focusRing}`}
          >
            Clear all filters
          </button>
        </div>
      )}
    </div>
  );
}
