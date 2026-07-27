import type { Metadata } from 'next';
import { display, text } from './fonts';
import { SiteStructuredData } from './components/StructuredData';
import {
  GOOGLE_SITE_VERIFICATION,
  OG_IMAGE_PATH,
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_TITLE,
  SITE_URL,
} from './lib/site';
import './globals.css';

export const metadata: Metadata = {
  // Without metadataBase, Next cannot resolve the relative URLs below into the
  // absolute ones canonical and og:image require — it emits a build warning and
  // drops them. Sourced from PUBLIC_SITE_URL, the same variable the API uses for
  // the RSS channel, so the two can't disagree about where the site lives.
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    // Subpages supply only their own name; this appends the brand once, so no
    // page has to remember to.
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  alternates: {
    canonical: '/',
    types: {
      'application/rss+xml': [
        { url: '/rss', title: `${SITE_NAME} RSS` },
      ],
    },
  },
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: '/',
    locale: 'en_US',
    images: [
      {
        url: OG_IMAGE_PATH,
        width: 1200,
        height: 630,
        alt: `${SITE_NAME} — San Jose Sharks news and rumors in one feed`,
      },
    ],
  },
  // Proves origin ownership to Google Search Console. Emitted on every page, so
  // verification does not depend on any single URL staying reachable.
  verification: {
    google: GOOGLE_SITE_VERIFICATION,
  },
  twitter: {
    card: 'summary_large_image',
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: [OG_IMAGE_PATH],
  },
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '32x32' },
      { url: '/favicon-32x32.png', type: 'image/png', sizes: '32x32' },
      { url: '/favicon-128x128.png', type: 'image/png', sizes: '128x128' },
      { url: '/favicon-512x512.png', type: 'image/png', sizes: '512x512' },
    ],
    apple: [
      { url: '/apple-touch-icon.png', sizes: '180x180' },
    ],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${display.variable} ${text.variable}`}>
      <body className="antialiased">
        <SiteStructuredData />
        {children}
      </body>
    </html>
  );
}
