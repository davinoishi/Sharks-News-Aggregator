'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';

export default function SubmitPage() {
  const [url, setUrl] = useState('');
  const [note, setNote] = useState('');
  const [state, setState] = useState<'idle' | 'submitting' | 'ok' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setState('submitting');
    setMessage('');
    try {
      const res = await fetch('/api/submit/link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim(), note: note.trim() || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState('error');
        setMessage(data.detail || data.error || 'Sorry, that link could not be submitted.');
        return;
      }
      setState('ok');
      setMessage('Thanks! Your link was received. It will be reviewed automatically and added to the feed if it is relevant.');
      setUrl('');
      setNote('');
    } catch {
      setState('error');
      setMessage('Something went wrong. Please try again.');
    }
  };

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-8">
          <Link href="/" className="flex items-center gap-4 mb-2 hover:opacity-80">
            <Image src="/logo.png" alt="San Jose Sharks Logo" width={48} height={48} className="object-contain" />
            <span className="text-xl font-semibold text-gray-900">Sharks News Aggregator</span>
          </Link>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-6 md:p-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Submit a link</h1>
          <p className="text-gray-600 mb-6">
            Found a Sharks story we missed? Share the link and it will go through the normal
            review process automatically — no account needed.
          </p>

          {state === 'ok' ? (
            <div className="rounded-md bg-green-50 border border-green-200 px-4 py-3 text-green-800">
              {message}
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => setState('idle')}
                  className="rounded-md bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
                >
                  Submit another
                </button>
                <Link
                  href="/"
                  className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Back to feed
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label htmlFor="url" className="block text-sm font-medium text-gray-700 mb-1">
                  Link URL
                </label>
                <input
                  id="url"
                  type="url"
                  required
                  placeholder="https://example.com/sharks-story"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
                />
              </div>
              <div>
                <label htmlFor="note" className="block text-sm font-medium text-gray-700 mb-1">
                  Note <span className="text-gray-400">(optional)</span>
                </label>
                <textarea
                  id="note"
                  rows={3}
                  placeholder="Anything we should know about this link?"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-teal-500 focus:outline-none focus:ring-1 focus:ring-teal-500"
                />
              </div>

              {state === 'error' && (
                <p className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                  {message}
                </p>
              )}

              <button
                type="submit"
                disabled={state === 'submitting' || !url.trim()}
                className="rounded-md bg-teal-700 px-5 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {state === 'submitting' ? 'Submitting…' : 'Submit link'}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-sm">
          <Link href="/" className="text-blue-600 hover:underline">
            ← Back to feed
          </Link>
        </p>
      </div>
    </main>
  );
}
