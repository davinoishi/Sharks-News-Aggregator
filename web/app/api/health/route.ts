import { NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../config';

export async function GET() {
  const url = `${INTERNAL_API_URL}/health`;

  try {
    const response = await fetch(url, {
      headers: {
        'Accept': 'application/json',
      },
      cache: 'no-store',
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
    console.error('Error proxying to backend /health:', error);
    return NextResponse.json(
      { error: 'Failed to fetch from backend' },
      { status: 502 }
    );
  }
}
