/**
 * Internal API configuration for server-side proxying.
 * This URL is used by Next.js API routes to fetch from the backend.
 * It should point to the backend's internal address (not public).
 */

// Default to localhost:8001 for local development
// In Docker, this should be set to the service name (e.g., http://api:8000)
export const INTERNAL_API_URL = process.env.INTERNAL_API_URL || 'http://localhost:8001';

// Server-side admin API key. Injected as X-Admin-API-Key when proxying to the
// backend's /admin/* endpoints. MUST NOT be exposed to the browser — never use
// a NEXT_PUBLIC_* name for this.
export const ADMIN_API_KEY = process.env.ADMIN_API_KEY || '';

/**
 * Best-effort real client IP for a proxied request.
 *
 * Reads the leftmost X-Forwarded-For entry (set by the upstream tunnel), then
 * falls back to request.ip. The backend independently validates that the value
 * came from a trusted proxy before honoring it.
 */
export function getClientIp(request: Request): string {
  const xff = request.headers.get('x-forwarded-for');
  if (xff) {
    const first = xff.split(',')[0].trim();
    if (first) return first;
  }
  // Next.js exposes .ip on the request behind some hosting platforms.
  const ip = (request as unknown as { ip?: string }).ip;
  return ip || '';
}
