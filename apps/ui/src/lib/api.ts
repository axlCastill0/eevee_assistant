/**
 * Backend API client.
 *
 * Requests go to /api/*, which nginx reverse-proxies to the FastAPI service
 * while injecting the X-API-Key header. The key is never present in this
 * bundle or anywhere else the browser can read — see infra/docker/ui/.
 */

export interface ServiceEntry {
  name: string
  healthy: boolean
  detail: string
  last_seen_s_ago: number | null
}

export interface ServicesResponse {
  all_healthy: boolean
  speech: string
  stale_after_s: number
  services: ServiceEntry[]
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Aborts rather than hanging forever if the backend stops responding mid-request. */
const TIMEOUT_MS = 4000

async function get<T>(path: string): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(`/api${path}`, {
      signal: controller.signal,
      // The dashboard must never show a cached status.
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })

    if (res.status === 401) {
      // nginx is not injecting the key, or it does not match the backend's.
      throw new ApiError('API key rejected by backend', 401)
    }
    // Gateway statuses mean nginx could not reach the backend at all — it is
    // down, not erroring. Saying "returned 502" would send you reading backend
    // logs that were never written.
    // (The Vite dev proxy reports an unreachable upstream as 500 instead, so
    // in `npm run dev` only, a dead backend shows as "Backend error". Not worth
    // mistranslating a real 500 to fix.)
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new ApiError('Backend unreachable', res.status)
    }
    // A genuine 500 from the backend. The most likely cause is API_KEY being
    // unset on the server, which auth.py reports as 500 by design.
    if (res.status === 500) {
      throw new ApiError('Backend error', 500)
    }
    if (!res.ok) {
      throw new ApiError(`Backend returned ${res.status}`, res.status)
    }

    return (await res.json()) as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError('Backend timed out')
    }
    throw new ApiError('Backend unreachable')
  } finally {
    window.clearTimeout(timer)
  }
}

export function fetchServices() {
  return get<ServicesResponse>('/services')
}
