/**
 * Timers, alarms and settings — polled from the app shell, not from a view.
 *
 * WHY IT LIVES IN App RATHER THAN THE DASHBOARD
 *   An alarm has to ring whatever page is on screen. If this hook were
 *   mounted by the Dashboard view, an alarm set for 7am would be silent
 *   whenever the panel happened to be left on Music, which is exactly when
 *   you need it. The top bar's status icons need the same data for the same
 *   reason.
 *
 * ONE POLL FOR THREE THINGS
 *   `/clock/state` returns all of it. Every field is in memory on the
 *   backend, so a 1 Hz poll over loopback is cheaper than the three requests
 *   it replaces.
 *
 * COUNTDOWNS ARE LOCAL
 *   `remaining_s` from the server is an anchor, not a clock. The displayed
 *   countdown is advanced locally between samples, so it ticks smoothly at
 *   1 Hz polling instead of stepping once a second with jitter.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchClockState, type ClockState, type TimerEntry } from './api'

const POLL_MS = 1000
const TICK_MS = 200

export interface ClockFeed {
  data: ClockState | null
  error: string | null
  /** Timers with `remaining_s` advanced locally since the last poll. */
  timers: TimerEntry[]
  ringingTimers: TimerEntry[]
  ringingAlarm: ClockState['alarms']['ringing']
  /** True when an alarm is set to go off within 24 hours. */
  alarmSoon: boolean
  /** Re-poll now. Called after every mutation so the UI never shows a stale
   *  list for a second after a tap. */
  refresh: () => void
}

export function useClockState(): ClockFeed {
  const [data, setData] = useState<ClockState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  // When the last snapshot arrived, in monotonic-ish browser time. Used to
  // age `remaining_s` without trusting the wall clock, which the Pi steps at
  // boot when NTP catches up.
  const receivedAt = useRef(0)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchClockState()
      receivedAt.current = performance.now()
      setData(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Backend unreachable')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  // Drives the local countdown. Separate from the poll so the digits move
  // five times a second while the network is touched once.
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), TICK_MS)
    return () => window.clearInterval(id)
  }, [])

  const ageS = data ? (performance.now() - receivedAt.current) / 1000 : 0
  void tick // the interval above is what re-renders; this reads it explicitly

  const timers = (data?.timers.timers ?? []).map((t) =>
    t.ringing ? t : { ...t, remaining_s: Math.max(0, t.remaining_s - ageS) },
  )

  const nextFire = data?.alarms.next_fire_in_s ?? null

  return {
    data,
    error,
    timers,
    ringingTimers: data?.timers.ringing ?? [],
    ringingAlarm: data?.alarms.ringing ?? null,
    alarmSoon: nextFire !== null && nextFire <= 24 * 3600,
    refresh: () => void refresh(),
  }
}

/** mm:ss, or h:mm:ss past an hour. Shared by the Dashboard and the top bar. */
export function countdown(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds))
  const s = total % 60
  const m = Math.floor(total / 60) % 60
  const h = Math.floor(total / 3600)
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}
