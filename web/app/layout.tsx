import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sharks News Aggregator',
  description: 'San Jose Sharks news and rumors in one feed',
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
