/**
 * Internal API configuration for server-side proxying.
 * This URL is used by Next.js API routes to fetch from the backend.
 * It should point to the backend's internal address (not public).
 */

// Default to localhost:8001 for local development
// In Docker, this should be set to the service name (e.g., http://api:8000)
export const INTERNAL_API_URL = process.env.INTERNAL_API_URL || 'http://localhost:8001';
