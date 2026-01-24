import Link from 'next/link';
import Image from 'next/image';

export default function LegalPage() {
  const lastUpdated = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

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
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Terms of Use and Privacy Policy
          </h1>
          <p className="text-sm text-gray-500 mb-8">Last updated: {lastUpdated}</p>

          <div className="prose prose-gray max-w-none">
            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">1. Overview</h2>
            <p className="text-gray-700 mb-4">
              Sharks News Aggregator (&quot;the Site&quot;) is an experimental, informational website
              that aggregates publicly available news, rumors, and links related to the San Jose
              Sharks from third-party sources.
            </p>
            <p className="text-gray-700 mb-4">
              The Site does not create original news content and does not host full articles. All
              links direct users to the original source.
            </p>
            <p className="text-gray-700 mb-4">
              By accessing or using the Site, you agree to the terms outlined below.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              2. Use at Your Own Risk
            </h2>
            <p className="text-gray-700 mb-4">
              The Site is provided &quot;as is&quot; and &quot;as available.&quot;
            </p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>Information may be incomplete, inaccurate, delayed, speculative, or outdated.</li>
              <li>
                Rumors and reports are aggregated from external sources and may not be verified.
              </li>
              <li>
                You are solely responsible for how you interpret or rely on any information
                presented.
              </li>
            </ul>
            <p className="text-gray-700 mb-4">
              The operator of this Site makes no guarantees regarding accuracy, completeness, or
              reliability.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              3. No Professional Advice
            </h2>
            <p className="text-gray-700 mb-4">
              Nothing on this Site constitutes professional, legal, medical, financial, or betting
              advice.
            </p>
            <p className="text-gray-700 mb-4">
              Any decisions you make based on information from the Site are made entirely at your
              own risk.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              4. Third-Party Content and Links
            </h2>
            <p className="text-gray-700 mb-4">
              The Site aggregates headlines and links from third-party websites, social platforms,
              and public sources.
            </p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>All content belongs to its respective owners.</li>
              <li>
                The Site does not control, endorse, or take responsibility for third-party content.
              </li>
              <li>
                Clicking a link will take you to an external website governed by its own terms and
                privacy policies.
              </li>
            </ul>
            <p className="text-gray-700 mb-4">
              If you believe a link or source should be removed, please contact the Site operator.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              5. Intellectual Property
            </h2>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>
                All third-party content remains the property of its original creators and
                publishers.
              </li>
              <li>The Site does not reproduce full articles or paywalled content.</li>
              <li>
                The Site&apos;s code is open source and available at:{' '}
                <a
                  href="https://github.com/davinoishi/Sharks-News-Aggregator"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  github.com/davinoishi/Sharks-News-Aggregator
                </a>
              </li>
            </ul>
            <p className="text-gray-700 mb-4">
              Unless otherwise stated, no license is granted to use the Site&apos;s branding or name
              without permission.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">6. Privacy Policy</h2>

            <h3 className="text-lg font-medium text-gray-900 mt-6 mb-3">6.1 Data Collection</h3>
            <p className="text-gray-700 mb-4">
              The Site does not intentionally collect, store, or process personal data.
            </p>
            <p className="text-gray-700 mb-2">Specifically:</p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>No user accounts</li>
              <li>No login information</li>
              <li>No names, emails, or identifiers</li>
              <li>No tracking cookies set by the Site</li>
            </ul>
            <p className="text-gray-700 mb-4">
              Basic server logs (such as IP addresses or request metadata) may be generated by
              hosting infrastructure for operational and security purposes only.
            </p>

            <hr className="my-8 border-gray-200" />

            <h3 className="text-lg font-medium text-gray-900 mt-6 mb-3">
              6.2 Cookies and Analytics
            </h3>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>The Site does not use advertising cookies.</li>
              <li>The Site does not run behavioral tracking or targeted advertising.</li>
              <li>If analytics are added in the future, this policy will be updated.</li>
            </ul>

            <hr className="my-8 border-gray-200" />

            <h3 className="text-lg font-medium text-gray-900 mt-6 mb-3">6.3 User Submissions</h3>
            <p className="text-gray-700 mb-2">If the Site allows users to submit links:</p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>Submitted URLs are processed for aggregation purposes only.</li>
              <li>No personal information is required or expected.</li>
              <li>Do not submit private, confidential, or sensitive information.</li>
            </ul>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              7. Availability and Changes
            </h2>
            <p className="text-gray-700 mb-4">
              The Site may be modified, suspended, or shut down at any time without notice.
            </p>
            <p className="text-gray-700 mb-4">
              Features, data sources, or functionality may change as the project evolves.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">
              8. Limitation of Liability
            </h2>
            <p className="text-gray-700 mb-2">To the fullest extent permitted by law:</p>
            <ul className="list-disc pl-6 text-gray-700 mb-4 space-y-2">
              <li>
                The Site operator shall not be liable for any damages, losses, or claims arising
                from use of the Site.
              </li>
              <li>
                This includes, but is not limited to, direct, indirect, incidental, or consequential
                damages.
              </li>
            </ul>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">9. Governing Law</h2>
            <p className="text-gray-700 mb-4">
              This Site is operated as a personal or experimental project. Any disputes shall be
              governed by applicable local laws, without regard to conflict of law principles.
            </p>

            <hr className="my-8 border-gray-200" />

            <h2 className="text-xl font-semibold text-gray-900 mt-8 mb-4">10. Contact</h2>
            <p className="text-gray-700 mb-4">
              For questions, concerns, or removal requests, please contact the Site operator via the
              GitHub repository:
            </p>
            <p className="text-gray-700">
              <a
                href="https://github.com/davinoishi/Sharks-News-Aggregator"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                github.com/davinoishi/Sharks-News-Aggregator
              </a>
            </p>
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
