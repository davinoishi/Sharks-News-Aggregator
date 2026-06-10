import Link from 'next/link';

export const metadata = {
  title: 'Admin',
  robots: { index: false, follow: false },
};

type AdminLink = { title: string; href: string; desc: string };

const groups: { heading: string; links: AdminLink[] }[] = [
  {
    heading: 'Sources & submissions',
    links: [
      { title: 'Source health', href: '/admin/sources', desc: 'All sources with health/status (rich view).' },
      { title: 'Submitted links', href: '/admin/view?endpoint=submissions&label=Submitted%20links', desc: 'User-submitted links + status breakdown — review and add sources.' },
      { title: 'Candidate sources', href: '/admin/view?endpoint=candidate-sources', desc: 'Domains queued for review.' },
    ],
  },
  {
    heading: 'Validation & LLM',
    links: [
      { title: 'Validation logs', href: '/admin/view?endpoint=validations&label=Validation%20logs', desc: 'Recent relevance/classification decisions.' },
      { title: 'Validation stats', href: '/admin/view?endpoint=validations/stats&label=Validation%20stats', desc: 'Aggregate approve/reject/error counts.' },
      { title: 'Rejected items', href: '/admin/view?endpoint=validations/rejected&label=Rejected%20validations', desc: 'Articles rejected by validation.' },
      { title: 'LLM report', href: '/admin/view?endpoint=validations/llm-report&label=LLM%20report', desc: 'LLM vs keyword comparison report.' },
      { title: 'LLM health', href: '/admin/view?endpoint=llm/health&label=LLM%20health', desc: 'OpenRouter health + model.' },
    ],
  },
  {
    heading: 'BlueSky',
    links: [
      { title: 'BlueSky health', href: '/admin/view?endpoint=bluesky/health&label=BlueSky%20health', desc: 'Posting service status.' },
      { title: 'BlueSky stats', href: '/admin/view?endpoint=bluesky/stats&label=BlueSky%20stats', desc: 'Post counts and activity.' },
      { title: 'BlueSky posts', href: '/admin/view?endpoint=bluesky/posts&label=BlueSky%20posts', desc: 'Recent posts.' },
    ],
  },
];

export default function AdminIndexPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto p-4 md:p-8">
        <div className="mb-6">
          <Link href="/" className="text-sm text-blue-600 hover:underline">
            ← Back to site
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 mt-2">Admin</h1>
          <p className="text-gray-600 text-sm mt-1">
            All pages here are protected by the admin login.
          </p>
        </div>

        <div className="space-y-8">
          {groups.map((group) => (
            <section key={group.heading}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
                {group.heading}
              </h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="block rounded-lg border border-gray-200 bg-white p-4 hover:border-blue-400 hover:shadow-sm transition"
                    >
                      <span className="block font-medium text-gray-900">{link.title}</span>
                      <span className="block text-sm text-gray-500 mt-1">{link.desc}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
