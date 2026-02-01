import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sharks News Aggregator',
  description: 'San Jose Sharks news and rumors in one feed',
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
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
