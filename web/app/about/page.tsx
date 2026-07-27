import type { Metadata } from 'next';
import Link from 'next/link';
import Image from 'next/image';
import { AuthorStructuredData } from '../components/StructuredData';
import { LOGO_ALT } from '../lib/branding';
import { pageMetadata } from '../lib/site';

export const metadata: Metadata = pageMetadata({
  title: 'About',
  description:
    'Why Sharks News Aggregator exists and who built it — a free, ad-free ' +
    'fan project pulling San Jose Sharks news and rumors into one feed.',
  path: '/about',
  socialTitle: 'About Sharks News Aggregator',
  socialDescription:
    'A free, ad-free Sharks news aggregator built by a fan, for fans.',
});

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-canvas">
      <AuthorStructuredData />
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        {/* Header */}
        <header className="mb-8">
          <Link href="/" className="flex items-center gap-4 mb-2 hover:opacity-80">
            <Image
              src="/logo.png"
              alt={LOGO_ALT}
              width={48}
              height={48}
              className="object-contain"
            />
            <span className="font-display text-wordmark uppercase text-content">
              Sharks News Aggregator
            </span>
          </Link>
        </header>

        {/* Content */}
        <div className="bg-surface border border-edge rounded-lg p-6 md:p-8">
          <h1 className="font-display text-title text-content mb-6">About</h1>

          <div className="doc">
            <p>
              I&apos;ve been a San Jose Sharks fan since day one and have lived most of my life in
              San Jose. Like a lot of fans, I spend way too much time bouncing between social
              media, blogs, and news sites just to keep up with Sharks news, rumors, and updates.
            </p>

            <p>So I built this.</p>

            <p>
              This site is a Sharks-focused news and rumor aggregator designed to save fans time.
              Instead of endlessly scrolling through your feeds, you can come here and quickly see
              what&apos;s happening, scan the headlines, and click through to the original sources
              you trust.
            </p>

            <p className="mb-2">The goal is simple:</p>
            <ul>
              <li>One place for Sharks news and rumors</li>
              <li>Fast to scan</li>
              <li>Links directly to the original reporting</li>
              <li>No clutter</li>
            </ul>

            <p>
              Right now, the site is completely free and has no ads. It&apos;s a fan project, built
              for other fans.
            </p>

            <hr />

            <h2>Who built this?</h2>

            <p>Hi, I&apos;m Davin.</p>

            <p>
              You can find all of my social media accounts here:{' '}
              <a
                href="https://linktr.ee/davinoishi"
                target="_blank"
                rel="noopener noreferrer"
                className="text-action hover:underline"
              >
                linktr.ee/davinoishi
              </a>
            </p>

            <p>
              If you enjoy the site and want to support ongoing development, you can also buy me a
              coffee here:{' '}
              <a
                href="https://www.buymeacoffee.com/davinoishi"
                target="_blank"
                rel="noopener noreferrer"
                className="text-action hover:underline"
              >
                buymeacoffee.com/davinoishi
              </a>
            </p>

            <p>
              Support is never required, but always appreciated.
            </p>

            <hr />

            <h2>Disclaimer</h2>

            <p>
              This is an independent, unofficial fan project. The site aggregates publicly
              available links and reports from third-party sources. I don&apos;t create or break
              news, and I don&apos;t claim accuracy beyond what the original sources provide.
            </p>

            <p>Use at your own risk, and always check the source.</p>
          </div>
        </div>

        {/* Back link */}
        <div className="mt-8 text-center">
          <Link href="/" className="tap-44 inline-flex items-center px-2 py-2 rounded-md text-action hover:underline">
            &larr; Back to News Feed
          </Link>
        </div>
      </div>
    </main>
  );
}
