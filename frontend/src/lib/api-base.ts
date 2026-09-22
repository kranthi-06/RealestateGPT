/**
 * API base URL resolution — shared by the browser client and server components.
 *
 * Production safety rule: a production build must NEVER contain an implicit
 * ``http://localhost`` dependency. Resolution order:
 *
 * 1. ``NEXT_PUBLIC_API_URL`` when set (the Vercel project supplies
 *    ``https://realestate-gpt-inky.vercel.app/api/backend``).
 * 2. Production build without that variable -> same-origin ``/api/backend``,
 *    which is exactly how the Vercel multi-service deployment exposes the
 *    FastAPI service (see the root ``vercel.json`` rewrites).
 * 3. Development only -> the local uvicorn default.
 */

export const SAME_ORIGIN_API_BASE = "/api/backend";
export const LOCAL_DEV_API_BASE = "http://localhost:8000";

/** True when an API base would point a deployed build at a developer machine. */
export function isLoopbackApiBase(base: string): boolean {
  const value = (base || "").trim();
  if (!value) return false;
  try {
    const url = new URL(value, "http://placeholder.invalid");
    return ["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"].includes(url.hostname);
  } catch {
    return false;
  }
}

export function resolveApiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL || "").trim();
  if (configured) return configured.replace(/\/+$/, "");
  if (process.env.NODE_ENV === "production") return SAME_ORIGIN_API_BASE;
  return LOCAL_DEV_API_BASE;
}
