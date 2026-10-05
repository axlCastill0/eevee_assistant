import { useCallback, useEffect, useState } from 'react'

/**
 * Theme control with three modes.
 *
 *   light  — forced light
 *   dark   — forced dark
 *   auto   — light from DAY_START to DAY_END, dark otherwise
 *
 * Two things make this harder than it looks on a kiosk:
 *
 * 1. The panel runs for months without a reload, so `auto` cannot be evaluated
 *    once at mount. A timer fires at the next boundary.
 *
 * 2. The Pi has no RTC. Before NTP syncs, the clock can read 1970 or a stale
 *    value from last boot, which would pick the wrong theme and then stay
 *    wrong until something re-rendered. Same class of bug the backend avoids
 *    by using a monotonic clock for heartbeat staleness. We detect an
 *    implausible clock, hold dark, and re-check until it looks sane.
 */

export type ThemeMode = 'light' | 'dark' | 'auto'
export type Resolved = 'light' | 'dark'

export const DAY_START = 8 // 08:00 — light from here
export const DAY_END = 18 // 18:00 — dark from here

const STORAGE_KEY = 'eevee.theme'

/** Anything before this means the clock has not synced yet. */
const PLAUSIBLE_YEAR = 2025

/** How often to re-check an implausible clock. */
const CLOCK_RECHECK_MS = 15_000

export function isDaytime(d: Date): boolean {
  const h = d.getHours()
  return h >= DAY_START && h < DAY_END
}

export function clockLooksSynced(d: Date = new Date()): boolean {
  return d.getFullYear() >= PLAUSIBLE_YEAR
}

function readStored(): ThemeMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'light' || raw === 'dark' || raw === 'auto') return raw
  } catch {
    // Private mode or blocked storage. Fall through to the default.
  }
  return 'auto'
}

/** ms until the next 08:00 or 18:00 boundary. */
function msUntilNextBoundary(now: Date): number {
  const next = new Date(now)
  next.setMinutes(0, 0, 0)

  const h = now.getHours()
  if (h < DAY_START) next.setHours(DAY_START)
  else if (h < DAY_END) next.setHours(DAY_END)
  else {
    next.setDate(next.getDate() + 1)
    next.setHours(DAY_START)
  }

  // Guard against a zero or negative wait, which would spin the timer.
  return Math.max(1000, next.getTime() - now.getTime())
}

export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(readStored)
  const [resolved, setResolved] = useState<Resolved>(() =>
    readStored() === 'light' ? 'light' : 'dark',
  )
  const [clockSynced, setClockSynced] = useState(clockLooksSynced)

  // Resolve mode -> concrete theme, and schedule the next flip.
  useEffect(() => {
    if (mode !== 'auto') {
      setResolved(mode)
      return
    }

    let timer: number | undefined

    const evaluate = () => {
      const now = new Date()

      if (!clockLooksSynced(now)) {
        // Hold dark: at 3am a surprise white screen is worse than a dark one
        // during the day, and this resolves itself within seconds of NTP.
        setResolved('dark')
        setClockSynced(false)
        timer = window.setTimeout(evaluate, CLOCK_RECHECK_MS)
        return
      }

      setClockSynced(true)
      setResolved(isDaytime(now) ? 'light' : 'dark')
      timer = window.setTimeout(evaluate, msUntilNextBoundary(now))
    }

    evaluate()
    return () => window.clearTimeout(timer)
  }, [mode])

  // Apply to <html> so the CSS variables swap and the crossfade runs.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolved)
  }, [resolved])

  const choose = useCallback((next: ThemeMode) => {
    setMode(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Not fatal — the theme just will not survive a reload.
    }
  }, [])

  /** Cycle light -> dark -> auto -> light. Used by the single-button form. */
  const cycle = useCallback(() => {
    const order: ThemeMode[] = ['light', 'dark', 'auto']
    choose(order[(order.indexOf(mode) + 1) % order.length])
  }, [mode, choose])

  return { mode, resolved, clockSynced, choose, cycle }
}
