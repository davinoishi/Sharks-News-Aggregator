'use client';

import { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { LOGO_ALT } from '../lib/branding';

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
    <main className="min-h-screen bg-canvas">
      <div className="max-w-2xl mx-auto p-4 md:p-8">
        {/* Header */}
        <header className="mb-8">
          <Link href="/" className="flex items-center gap-4 mb-2 hover:opacity-80">
            <Image src="/logo.png" alt={LOGO_ALT} width={48} height={48} className="object-contain" />
            <span className="font-display text-wordmark uppercase text-content">Sharks News Aggregator</span>
          </Link>
        </header>

        <div className="bg-surface border border-edge rounded-lg p-6 md:p-8">
          <h1 className="font-display text-title text-content mb-2">Submit a link</h1>
          <p className="text-body text-content-secondary mb-6 max-w-[60ch]">
            Found a Sharks story we missed? Share the link and it will go through the normal
            review process automatically — no account needed.
          </p>

          {state === 'ok' ? (
            <div className="rounded-md bg-positive border border-positive-edge px-4 py-3 text-body text-positive-fg">
              {message}
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => setState('idle')}
                  className="tap-44 inline-flex items-center rounded-md bg-action px-4 py-2.5 text-ui text-on-action hover:bg-action-hover"
                >
                  Submit another
                </button>
                <Link
                  href="/"
                  className="tap-44 inline-flex items-center rounded-md border border-edge-strong px-4 py-2.5 text-ui text-content-secondary hover:bg-surface-sunken"
                >
                  Back to feed
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <label htmlFor="url" className="block text-ui text-content-secondary mb-1.5">
                  Link URL
                </label>
                <input
                  id="url"
                  type="url"
                  required
                  placeholder="https://example.com/sharks-story"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="w-full min-h-[44px] rounded-md border border-edge-strong bg-surface px-3 py-2.5 text-body text-content focus:border-focus focus:outline-none focus:ring-1 focus:ring-focus"
                />
              </div>
              <div>
                <label htmlFor="note" className="block text-ui text-content-secondary mb-1.5">
                  Note <span className="font-normal text-content-muted">(optional)</span>
                </label>
                <textarea
                  id="note"
                  rows={3}
                  placeholder="Anything we should know about this link?"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="w-full min-h-[44px] rounded-md border border-edge-strong bg-surface px-3 py-2.5 text-body text-content focus:border-focus focus:outline-none focus:ring-1 focus:ring-focus"
                />
              </div>

              {state === 'error' && (
                <p className="rounded-md bg-critical border border-critical-edge px-3 py-2 text-ui font-normal text-critical-fg">
                  {message}
                </p>
              )}

              <button
                type="submit"
                disabled={state === 'submitting' || !url.trim()}
                className="tap-44 inline-flex items-center rounded-md bg-action px-5 py-2.5 text-ui text-on-action hover:bg-action-hover disabled:bg-control disabled:text-content-muted disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
              >
                {state === 'submitting' ? 'Submitting…' : 'Submit link'}
              </button>
            </form>
          )}
        </div>

        <p className="mt-6 text-center text-ui">
          <Link href="/" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
            ← Back to feed
          </Link>
        </p>
      </div>
    </main>
  );
}
