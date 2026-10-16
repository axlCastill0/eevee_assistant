/**
 * "Nobody has touched this for a while."
 *
 * Used for the screen's auto-sleep. Deliberately listens for POINTER and key
 * events only, not mousemove: this panel has no mouse, and on the one machine
 * that does (a dev laptop) a stray cursor drift should not count as someone
 * being in the room.
 *
 * A timeout of 0 disables it and the hook never reports idle, which is what
 * makes "never" a real setting rather than a very long timer.
 */
import { useEffect, useRef, useState } from 'react'

const EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart'] as const

export function useIdle(timeoutMs: number): boolean {
  const [idle, setIdle] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (timeoutMs <= 0) {
      setIdle(false)
      return
    }

    const reset = () => {
      setIdle(false)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setIdle(true), timeoutMs)
    }

    reset()
    for (const name of EVENTS) {
      window.addEventListener(name, reset, { passive: true })
    }

    return () => {
      window.clearTimeout(timer.current)
      for (const name of EVENTS) window.removeEventListener(name, reset)
    }
  }, [timeoutMs])

  return idle
}
