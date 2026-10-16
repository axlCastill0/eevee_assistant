/**
 * Now-playing state, polled.
 *
 * WHY POLLING HERE, WHEN THE VOICE PILL IS PUSHED
 *   The pill is pushed because being 1.5s late makes the user talk to a
 *   pipeline that is not recording. Nothing on this page is like that: the
 *   progress bar is advanced from the clock between samples, and a track
 *   change arriving a second late is invisible. The poll goes to this
 *   backend, not to Spotify -- the backend holds a TTL'd snapshot and is the
 *   only thing that talks to Spotify, so a dashboard left open all day costs
 *   Spotify one request every few seconds regardless of how fast we poll.
 *
 * PROGRESS
 *   Each snapshot carries the server's `fetched_at`, so elapsed time is
 *   measured from when SPOTIFY was asked, not from when the response landed.
 *   The UI then advances it locally while playing. That keeps the bar smooth
 *   on a 1s poll and stops it jumping backwards when a response is slow.
 *
 * OPTIMISM
 *   A tap flips `is_playing` locally and refetches immediately. A ~300ms
 *   round trip on a touch control reads as a broken button otherwise.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchNowPlaying,
  sendSpotifyCommand,
  type CommandResult,
  type NowPlaying,
  type SpotifyAction,
} from './api'

/** How often to ask the backend. Cheap: localhost, and served from cache. */
const POLL_MS = 1000

/** How often the progress readout is recomputed. 4x a second is enough for a
 *  second counter that never visibly lags, and cheap enough on a Pi. */
const TICK_MS = 250

export interface SpotifyFeed {
  data: NowPlaying | null
  /** True until the first response, so the view can avoid flashing "nothing
   *  is playing" during startup. */
  loading: boolean
  /** The backend itself could not be reached (as opposed to Spotify). */
  error: string | null
  /** Interpolated playback position, milliseconds. */
  progressMs: number
  /** What the last control press resulted in, for a transient toast. Cleared
   *  after a few seconds. */
  notice: CommandResult['status'] | null
  send: (action: SpotifyAction) => void
  pending: boolean
}

export function useSpotify(active: boolean): SpotifyFeed {
  const [data, setData] = useState<NowPlaying | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [progressMs, setProgressMs] = useState(0)
  const [notice, setNotice] = useState<CommandResult['status'] | null>(null)
  const [pending, setPending] = useState(false)

  // Anchor for interpolation: the snapshot's position, and the local clock
  // reading that corresponds to it. performance.now() because it cannot jump
  // when the Pi's wall clock is corrected by NTP after boot.
  const anchor = useRef<{ atMs: number; posMs: number; playing: boolean }>({
    atMs: 0,
    posMs: 0,
    playing: false,
  })

  const apply = useCallback((snapshot: NowPlaying) => {
    setData(snapshot)
    setError(null)

    const pos = snapshot.progress_ms ?? 0
    // Account for the age of the snapshot: the backend may have fetched it up
    // to its TTL ago, and the position has moved on since.
    const ageMs =
      snapshot.fetched_at && snapshot.is_playing
        ? Math.max(0, Math.min(10_000, Date.now() - snapshot.fetched_at * 1000))
        : 0

    anchor.current = {
      atMs: performance.now(),
      posMs: pos + ageMs,
      playing: Boolean(snapshot.is_playing),
    }
    setProgressMs(anchor.current.posMs)
  }, [])

  const refresh = useCallback(async () => {
    try {
      apply(await fetchNowPlaying())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backend unreachable')
    } finally {
      setLoading(false)
    }
  }, [apply])

  // Polling stops when the view is not mounted/visible. The music page is one
  // of two, and polling a page nobody is looking at is pure SD-card-free
  // waste -- but it is still waste.
  useEffect(() => {
    if (!active) return
    void refresh()
    const id = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(id)
  }, [active, refresh])

  // Local advance between samples.
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      const { atMs, posMs, playing } = anchor.current
      if (!playing) return
      const limit = data?.item?.duration_ms ?? Number.MAX_SAFE_INTEGER
      setProgressMs(Math.min(limit, posMs + (performance.now() - atMs)))
    }, TICK_MS)
    return () => window.clearInterval(id)
  }, [active, data?.item?.duration_ms])

  const send = useCallback(
    (action: SpotifyAction) => {
      setPending(true)

      // Optimistic flip for the one control whose effect is visible instantly.
      // Skip and next deliberately do NOT fake a track change: guessing the
      // next title wrongly is worse than a one-poll wait.
      setData((prev) => {
        if (!prev || prev.status !== 'ok') return prev
        if (action === 'play') return { ...prev, is_playing: true }
        if (action === 'pause') return { ...prev, is_playing: false }
        if (action === 'toggle') return { ...prev, is_playing: !prev.is_playing }
        return prev
      })
      if (action === 'play' || action === 'toggle' || action === 'pause') {
        anchor.current = {
          atMs: performance.now(),
          posMs: progressMs,
          playing: action === 'play' || (action === 'toggle' && !data?.is_playing),
        }
      }

      void (async () => {
        try {
          const result = await sendSpotifyCommand(action)
          // 'ok' needs no announcement; the panel itself is the feedback.
          setNotice(result.status === 'ok' ? null : result.status)
        } catch {
          setNotice('unreachable')
        } finally {
          setPending(false)
          // Spotify needs a moment to settle, especially on a skip: asking
          // immediately often returns the previous track still.
          window.setTimeout(() => void refresh(), 350)
        }
      })()
    },
    [data?.is_playing, progressMs, refresh],
  )

  // Notices are transient. Keeping one on screen after the user has moved on
  // would misreport the current state.
  useEffect(() => {
    if (!notice) return
    const id = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(id)
  }, [notice])

  return { data, loading, error, progressMs, notice, send, pending }
}
