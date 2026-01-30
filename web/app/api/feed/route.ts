import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../config';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const url = `${INTERNAL_API_URL}/feed?${searchParams.toString()}`;

  try {
    const response = await fetch(url, {
      headers: {
        'Accept': 'application/json',
      },
      cache: 'no-store',  // Disable caching to ensure fresh data on each request
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error proxying to backend /feed:', error);
    return NextResponse.json(
      { error: 'Failed to fetch from backend' },
      { status: 502 }
    );
  }
}
