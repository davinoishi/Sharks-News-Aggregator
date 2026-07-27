import type { Metadata } from 'next';
import { pageOpenGraph } from '../lib/site';

/**
 * Metadata carrier for /submit.
 *
 * `submit/page.tsx` is a client component (it owns the form's state), and a
 * client component cannot export `metadata`. A layout is the standard way to
 * attach it without turning the page into a server/client wrapper pair for the
 * sake of four static strings.
 */
export const metadata: Metadata = {
  title: 'Submit a Link',
  description:
    'Found a San Jose Sharks story the feed missed? Submit the link — no ' +
    'account needed. Submissions go through the same automated review as ' +
    'every other source.',
  alternates: { canonical: '/submit' },
  openGraph: pageOpenGraph({
    title: 'Submit a Sharks story',
    description: 'Send a link the aggregator missed. No account needed.',
    path: '/submit',
  }),
};

export default function SubmitLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
