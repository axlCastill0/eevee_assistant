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

/** Lyrics for the current track, from LRCLIB via the backend.
 *
 *  `idle` means nothing is playing; `none` means nobody has lyrics for this
 *  track; `instrumental` means the database says there are none to have.
 *  Only `ok` carries lines, and only `synced` lines have a `t`. */
export type LyricsStatus = 'ok' | 'none' | 'instrumental' | 'idle' | 'unreachable'

export interface LyricLine {
  /** Seconds into the track. Null on an unsynced set. */
  t: number | null
  text: string
}

export interface Lyrics {
  status: LyricsStatus
  track_id?: string
  synced?: boolean
  lines?: LyricLine[]
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

// --- timers, alarms, settings ---------------------------------------------

export interface TimerEntry {
  id: string
  label: string
  duration_s: number
  remaining_s: number
  ringing: boolean
  /** Held: `remaining_s` is frozen and the timer will not fire. */
  paused: boolean
  /** Wall-clock time this timer ends, pre-formatted. Null once it has fired,
   *  and null while paused — a countdown that is not counting has no end. */
  ends_at: string | null
}

export interface AlarmEntry {
  weekday: number
  day: string
  hour: number
  minute: number
  enabled: boolean
  /** Pre-formatted AM/PM, so the panel and anything spoken agree. */
  label: string
  next_fire_in_s: number | null
}

/** Current conditions. Every non-answer is a `status`, not an HTTP error:
 *  "no location set" and "Open-Meteo unreachable" need different words. */
export interface WeatherState {
  status: 'ok' | 'unconfigured' | 'unavailable'
  temp?: number
  feels_like?: number
  description?: string
  is_day?: boolean
  place?: string
  /** Raw WMO code. The icon is chosen from this, not from `description` —
   *  the wording groups codes that want different glyphs. */
  code?: number
  units?: 'celsius' | 'fahrenheit'
}

/** The one Wake-on-LAN target. `online` is null when no WOL_HOST is set to
 *  probe — the panel then says "status unknown" rather than drawing a
 *  confident offline dot it has not earned. */
export interface WakeState {
  configured: boolean
  name: string
  mac: string
  online: boolean | null
  probe_host: string
  /** Ports the backend tries, in order. Empty when no probe host is set. */
  probe_ports?: number[]
}

export interface WakeResult extends WakeState {
  sent: boolean
  /** A sentence, worded by the backend so the panel and the assistant agree. */
  detail: string
}

export interface SoundEntry {
  file: string
  label: string
}

export interface ScreenState {
  on: boolean
  changed_at: number
  source: string
  /** Held awake against the idle timer. Nothing else is affected. */
  locked: boolean
}

export interface ClockState {
  timers: { timers: TimerEntry[]; ringing: TimerEntry[] }
  alarms: {
    alarms: AlarmEntry[]
    ringing: AlarmEntry | null
    next_fire_in_s: number | null
  }
  settings: {
    timer_sound: string
    alarm_sound: string
    /** The interval timer's cue. Short: it plays four times a phase. */
    training_sound: string
    /** Minutes of no touch before the panel blanks. "0" = never. */
    screen_timeout_min: string
    sounds: SoundEntry[]
    media_dir: string
  }
  screen: ScreenState
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
  return send<T>('POST', path, body)
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(`/api${path}`, {
      method,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
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

async function put<T>(path: string, body: unknown): Promise<T> {
  return send<T>('PUT', path, body)
}

async function del<T>(path: string): Promise<T> {
  return send<T>('DELETE', path)
}

export function fetchServices() {
  return get<ServicesResponse>('/services')
}

export function fetchClockState() {
  return get<ClockState>('/clock/state')
}

export function createTimer(durationS: number) {
  return post<TimerEntry>('/clock/timers', { duration_s: durationS })
}

export function deleteTimer(id: string) {
  return del<{ status: string }>(`/clock/timers/${id}`)
}

/** Send the state the panel WANTS, not a verb: a double tap then settles on
 *  the same thing instead of toggling twice. */
export function setTimerPaused(id: string, paused: boolean) {
  return post<TimerEntry>(`/clock/timers/${id}/pause`, { paused })
}

export function stopRingingTimers() {
  return post<{ stopped: number }>('/clock/timers/stop-all', {})
}

export function updateAlarm(
  weekday: number,
  values: { hour?: number; minute?: number; enabled?: boolean },
) {
  return put<AlarmEntry>(`/clock/alarms/${weekday}`, values)
}

export function stopAlarm() {
  return post<{ stopped: boolean }>('/clock/alarms/stop', {})
}

export function updateSettings(values: {
  timer_sound?: string
  alarm_sound?: string
  training_sound?: string
  screen_timeout_min?: string
}) {
  return put<ClockState['settings']>('/clock/settings', values)
}

/** `source` is logged by the backend: it is the first thing worth knowing
 *  when a panel blanks for no apparent reason. */
export function setScreen(on: boolean, source: string) {
  return post<ScreenState>('/screen', { on, source })
}

/** Hold the screen awake against the idle timer, or release it. */
export function setScreenLock(locked: boolean, source: string) {
  return post<ScreenState>('/screen/lock', { locked, source })
}

/** Same-origin audio, streamed by the backend out of the media directory. */
export function soundUrl(file: string) {
  return `/api/clock/sounds/${encodeURIComponent(file)}`
}

export function fetchWeather() {
  return get<WeatherState>('/weather')
}

export function fetchWake() {
  return get<WakeState>('/wake')
}

export function sendWake() {
  return post<WakeResult>('/wake', {})
}

export function fetchNowPlaying() {
  return get<NowPlaying>('/spotify/now-playing')
}

export function fetchLyrics() {
  return get<Lyrics>('/spotify/lyrics')
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
