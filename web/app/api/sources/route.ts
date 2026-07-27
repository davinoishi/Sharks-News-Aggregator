import { NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../config';

// The outlet list changes only when a source is added or disabled, so it is
// cached far longer than the feed. Revalidated hourly.
export const revalidate = 3600;

export async function GET() {
  const url = `${INTERNAL_API_URL}/sources`;

  try {
    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      next: { revalidate: 3600 },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('Error proxying to backend /sources:', error);
    return NextResponse.json(
      { error: 'Failed to fetch from backend' },
      { status: 502 }
    );
  }
}
