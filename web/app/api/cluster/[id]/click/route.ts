import { NextRequest, NextResponse } from 'next/server';
import { INTERNAL_API_URL } from '../../../config';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const url = `${INTERNAL_API_URL}/cluster/${id}/click`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
      },
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
    console.error(`Error proxying to backend /cluster/${id}/click:`, error);
    return NextResponse.json(
      { error: 'Failed to record click' },
      { status: 502 }
    );
  }
}
