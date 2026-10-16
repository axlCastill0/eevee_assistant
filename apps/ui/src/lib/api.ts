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

/** Playback snapshot. `status` carries every non-playing condition, because a
 *  panel has to tell "paused" from "not connected" from "Spotify is down", and
 *  HTTP codes cannot express that without colliding with the generic
 *  backend-unreachable handling above. */
export type SpotifyStatus =
  | 'ok'
  | 'idle'
  | 'unconfigured'
  | 'unauthorized'
  | 'unreachable'
  | 'rate_limited'

export interface SpotifyItem {
  kind: 'track' | 'episode'
  id: string | null
  title: string
  artist: string
  album: string
  duration_ms: number
  /** Cover id, to be fetched from /api/spotify/art/<id>. Null for the rare
   *  track with no artwork. */
  art_id: string | null
}

export interface NowPlaying {
  status: SpotifyStatus
  is_playing?: boolean
  progress_ms?: number
  /** Server wall clock when Spotify was last asked. The progress bar advances
   *  from this, not from when the response arrived. */
  fetched_at?: number
  device?: { name: string; type: string; volume_percent: number | null }
  item?: SpotifyItem
  /** Set when a fetch failed and this is the last good snapshot. */
  degraded?: 'unreachable' | 'rate_limited'
}

export type SpotifyAction = 'previous' | 'next' | 'play' | 'pause' | 'toggle'

export interface CommandResult {
  status:
    | 'ok'
    | 'no_device'
    | 'premium_required'
    | 'unauthorized'
    | 'unconfigured'
    | 'rate_limited'
    | 'unreachable'
  action?: string
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

async function post<T>(path: string, body: unknown): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(`/api${path}`, {
      method: 'POST',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new ApiError(`Backend returned ${res.status}`, res.status)
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

export function fetchNowPlaying() {
  return get<NowPlaying>('/spotify/now-playing')
}

export function sendSpotifyCommand(action: SpotifyAction) {
  return post<CommandResult>('/spotify/command', { action })
}

export function fetchSpotifyLogin() {
  return get<{ authorize_url: string; redirect_uri: string }>('/spotify/login')
}

/** Same-origin cover art, proxied by the backend. Immutable and cached for a
 *  year, so re-rendering the same track costs nothing. */
export function artUrl(artId: string) {
  return `/api/spotify/art/${artId}`
}
