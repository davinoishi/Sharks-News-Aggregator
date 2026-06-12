import { NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../api/config';

// Published at /rss (not /api/rss) so feed readers can subscribe at a clean URL.
// Re-validated by Next every 5 minutes; the backend also sets a 5-minute
// Cache-Control on its response.
export const revalidate = 300;

export async function GET() {
  const url = `${INTERNAL_API_URL}/rss`;

  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/rss+xml' },
      next: { revalidate: 300 },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const xml = await response.text();
    return new NextResponse(xml, {
      status: 200,
      headers: {
        'Content-Type': 'application/rss+xml; charset=utf-8',
        'Cache-Control': 'public, max-age=300, s-maxage=300',
      },
    });
  } catch (error) {
    console.error('Error proxying to backend /rss:', error);
    return NextResponse.json(
      { error: 'Failed to fetch from backend' },
      { status: 502 }
    );
  }
}
