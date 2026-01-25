import Link from 'next/link';
import Image from 'next/image';

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        {/* Header */}
        <div className="mb-8">
          <Link href="/" className="flex items-center gap-4 mb-2 hover:opacity-80">
            <Image
              src="/logo.png"
              alt="San Jose Sharks Logo"
              width={48}
              height={48}
              className="object-contain"
            />
            <span className="text-xl font-semibold text-gray-900">
              Sharks News Aggregator
            </span>
          </Link>
        </div>

        {/* Content */}
        <div className="bg-white border border-gray-200 rounded-lg p-6 md:p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-6">About</h1>

          <div className="prose prose-gray max-w-none">
            <p className="text-gray-700 mb-4">
              I&apos;ve been a San Jose Sharks fan since day one and have lived most of my life in
              San Jose. Like a lot of fans, I spend way too much time bouncing between social
              media, blogs, and news sites just to keep up with Sharks news, rumors, and updates.
            </p>

            <p className="text-gray-700 mb-4">So I built this.</p>

            <p className="text-gray-700 mb-4">
              This site is a Sharks-focused news and rumor aggregator designed to save fans time.
              Instead of endlessly scrolling through your feeds, you can come here and quickly see
              what&apos;s happening, scan the headlines, and click through to the original sources
              you trust.
            </p>

            <p className="text-gray-700 mb-2">The goal is simple:</p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-1">
              <li>One place for Sharks news and rumors</li>
              <li>Fast to scan</li>
              <li>Links directly to the original reporting</li>
              <li>No clutter</li>
            </ul>

            <p className="text-gray-700 mb-4">
              Right now, the site is completely free and has no ads. It&apos;s a fan project, built
              for other fans.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">Who built this?</h2>

            <p className="text-gray-700 mb-4">Hi, I&apos;m Davin.</p>

            <p className="text-gray-700 mb-4">
              You can find all of my social media accounts here:{' '}
              <a
                href="https://linktr.ee/davinoishi"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                linktr.ee/davinoishi
              </a>
            </p>

            <p className="text-gray-700 mb-4">
              If you enjoy the site and want to support ongoing development, you can also buy me a
              coffee here:{' '}
              <a
                href="https://www.buymeacoffee.com/davinoishi"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                buymeacoffee.com/davinoishi
              </a>
            </p>

            <p className="text-gray-700 mb-4">
              Support is never required, but always appreciated.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">Disclaimer</h2>

            <p className="text-gray-700 mb-4">
              This is an independent, unofficial fan project. The site aggregates publicly
              available links and reports from third-party sources. I don&apos;t create or break
              news, and I don&apos;t claim accuracy beyond what the original sources provide.
            </p>

            <p className="text-gray-700">Use at your own risk, and always check the source.</p>
          </div>
        </div>

        {/* Back link */}
        <div className="mt-8 text-center">
          <Link href="/" className="text-blue-600 hover:underline">
            &larr; Back to News Feed
          </Link>
        </div>
      </div>
    </main>
  );
}
