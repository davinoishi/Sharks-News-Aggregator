import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../../../config';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const since = searchParams.get('since');
  const queryString = since ? `?since=${since}` : '';
  const url = `${INTERNAL_API_URL}/admin/validations/llm-report${queryString}`;

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
    console.error('Error proxying to backend /admin/validations/llm-report:', error);
    return NextResponse.json(
      { error: 'Failed to fetch from backend' },
      { status: 502 }
    );
  }
}
