import type { Metadata } from 'next';
import { pageMetadata } from '../lib/site';

/**
 * Metadata carrier for /submit.
 *
 * `submit/page.tsx` is a client component (it owns the form's state), and a
 * client component cannot export `metadata`. A layout is the standard way to
 * attach it without turning the page into a server/client wrapper pair for the
 * sake of four static strings.
 */
export const metadata: Metadata = pageMetadata({
  title: 'Submit a Link',
  description:
    'Found a San Jose Sharks story the feed missed? Submit the link — no ' +
    'account needed. Submissions go through the same automated review as ' +
    'every other source.',
  path: '/submit',
  socialTitle: 'Submit a Sharks story',
  socialDescription: 'Send a link the aggregator missed. No account needed.',
});

export default function SubmitLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
