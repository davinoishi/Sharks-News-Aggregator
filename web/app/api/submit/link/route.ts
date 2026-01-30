import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../../config';

export async function POST(request: NextRequest) {
  const url = `${INTERNAL_API_URL}/submit/link`;

  try {
    const body = await request.json();

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      return NextResponse.json(error, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error proxying to backend /submit/link:', error);
    return NextResponse.json(
      { error: 'Failed to submit link' },
      { status: 502 }
    );
  }
}
