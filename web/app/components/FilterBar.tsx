'use client';

import { useState } from 'react';

interface FilterBarProps {
  onFilterChange: (filters: { tags?: string; since?: string }) => void;
}

const TAG_OPTIONS = [
  { value: 'news', label: 'News' },
  { value: 'rumors-press', label: 'Rumors (Press)' },
  { value: 'rumors-other', label: 'Rumors (Other)' },
  { value: 'trade', label: 'Trade' },
  { value: 'injury', label: 'Injury' },
  { value: 'lineup', label: 'Lineup' },
  { value: 'signing', label: 'Signing' },
  { value: 'game', label: 'Game' },
];

const TIME_OPTIONS = [
  { value: '', label: 'All time' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
];

export function FilterBar({ onFilterChange }: FilterBarProps) {
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [timeFilter, setTimeFilter] = useState('');

  const handleTagToggle = (tag: string) => {
    const newTags = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];

    setSelectedTags(newTags);
    onFilterChange({
      tags: newTags.join(',') || undefined,
      since: timeFilter || undefined,
    });
  };

  const handleTimeChange = (time: string) => {
    setTimeFilter(time);
    onFilterChange({
      tags: selectedTags.join(',') || undefined,
      since: time || undefined,
    });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
      <div className="mb-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">Filter by tags:</h3>
        <div className="flex flex-wrap gap-2">
          {TAG_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => handleTagToggle(option.value)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${
                selectedTags.includes(option.value)
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium text-gray-700 mb-2">Time range:</h3>
        <div className="flex flex-wrap gap-2">
          {TIME_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => handleTimeChange(option.value)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${
                timeFilter === option.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {(selectedTags.length > 0 || timeFilter) && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <button
            onClick={() => {
              setSelectedTags([]);
              setTimeFilter('');
              onFilterChange({});
            }}
            className="text-sm text-blue-600 hover:text-blue-700"
          >
            Clear all filters
          </button>
        </div>
      )}
    </div>
  );
}
