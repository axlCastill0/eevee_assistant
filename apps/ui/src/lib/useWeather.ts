/**
 * Current conditions, polled slowly.
 *
 * WHY A HOOK OF ITS OWN, AND NOT PART OF useClockState
 *   `/clock/state` is polled once a second because an alarm has to ring on
 *   time. Weather is cached for ten minutes on the backend and does not
 *   change faster than that, so asking at the same rate would be 600 pointless
 *   requests an hour -- and a cache miss there blocks on Open-Meteo, inside
 *   the poll that rings alarms. Separate hook, separate interval.
 *
 * WHY IT KEEPS THE LAST GOOD READING
 *   The Pi may lose wifi for a minute. Blanking the card would make the home
 *   screen flicker between two layouts; a slightly old temperature is a
 *   better answer than no temperature, which is the same posture the backend
 *   takes with its own cache.
 */
import { useEffect, useState } from 'react'
import { fetchWeather, type WeatherState } from './api'

// Half the backend's 600s cache, so the panel picks up a refresh within one
// interval of it happening without ever being the reason for a fetch.
const POLL_MS = 5 * 60_000

export function useWeather(): WeatherState | null {
  const [data, setData] = useState<WeatherState | null>(null)

  useEffect(() => {
    let alive = true

    const load = async () => {
      try {
        const next = await fetchWeather()
        // A transient failure must not replace a good reading with a worse
        // one: only overwrite when we actually have conditions, or when there
        // is nothing on screen yet to protect.
        if (!alive) return
        setData((prev) =>
          next.status === 'ok' || prev === null ? next : prev,
        )
      } catch {
        // Backend unreachable. The TopBar already says so; this card simply
        // keeps what it had.
      }
    }

    void load()
    const id = window.setInterval(() => void load(), POLL_MS)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [])

  return data
}

/** WMO code -> a glyph name this project draws. Grouped for the picture
 *  rather than for the sentence: "drizzling" and "pouring" share a word in
 *  the spoken answer and want different icons here. */
export type WeatherIcon =
  | 'clear'
  | 'partly'
  | 'cloud'
  | 'fog'
  | 'drizzle'
  | 'rain'
  | 'snow'
  | 'storm'

export function weatherIcon(code: number | undefined): WeatherIcon {
  if (code === undefined) return 'cloud'
  if (code === 0 || code === 1) return 'clear'
  if (code === 2) return 'partly'
  if (code === 3) return 'cloud'
  if (code === 45 || code === 48) return 'fog'
  if (code >= 51 && code <= 57) return 'drizzle'
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return 'rain'
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'snow'
  if (code >= 95) return 'storm'
  return 'cloud'
}
