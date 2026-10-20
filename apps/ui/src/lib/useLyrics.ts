/**
 * Lyrics for the current track.
 *
 * ONE FETCH PER TRACK, NOT PER POLL
 *   The backend caches per track id and the lines never change, so this asks
 *   once when the track changes and then not again. It is keyed on the track
 *   id rather than on the title, because a live version and the studio cut
 *   share a title and must not share lyrics.
 *
 * WHY IT MAY RETRY
 *   /spotify/lyrics reads the backend's CACHED playback snapshot, which can
 *   still be the previous track for up to a second after a skip. The answer
 *   carries the track id it is actually about, so a mismatch is detectable --
 *   and is retried rather than shown, because lyrics for the song that just
 *   ended scrolling under the one now playing is the worst possible failure
 *   for this feature.
 */
import { useEffect, useState } from 'react'
import { fetchLyrics, type Lyrics } from './api'

const RETRY_MS = 1200
const MAX_ATTEMPTS = 3

export function useLyrics(trackId: string | null, active: boolean): Lyrics | null {
  const [data, setData] = useState<Lyrics | null>(null)

  useEffect(() => {
    if (!active || !trackId) {
      setData(null)
      return
    }

    let cancelled = false
    let timer = 0

    // Cleared on every track change: a null result is "still looking", which
    // is what disables the button until there is an answer about THIS song.
    setData(null)

    const attempt = (n: number) => {
      void fetchLyrics().then(
        (result) => {
          if (cancelled) return
          if (result.track_id && result.track_id !== trackId && n < MAX_ATTEMPTS) {
            timer = window.setTimeout(() => attempt(n + 1), RETRY_MS)
            return
          }
          setData(result)
        },
        () => {
          if (!cancelled) setData({ status: 'unreachable' })
        },
      )
    }

    attempt(1)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [trackId, active])

  return data
}

/** Index of the line being sung at `progressMs`, or -1.
 *
 *  Linear from the start rather than a binary search: a long song is a few
 *  hundred lines, this runs once a render, and the version that is obviously
 *  correct is worth more here than the clever one.
 */
export function activeLine(lines: { t: number | null }[], progressMs: number): number {
  const at = progressMs / 1000
  let index = -1
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].t
    if (t === null || t > at) break
    index = i
  }
  return index
}
