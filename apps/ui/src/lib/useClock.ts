import { useEffect, useState } from 'react'

/**
 * Ticking clock, aligned to the second boundary.
 *
 * A plain 1000ms interval drifts and makes the seconds digit skip or repeat.
 * Scheduling each tick to land just after the next whole second keeps it
 * visually correct over a run measured in months.
 */
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    let timer: number

    const tick = () => {
      const d = new Date()
      setNow(d)
      // +5ms of slack so we land after the boundary, not exactly on it.
      timer = window.setTimeout(tick, 1000 - d.getMilliseconds() + 5)
    }

    tick()
    return () => window.clearTimeout(timer)
  }, [])

  return now
}
