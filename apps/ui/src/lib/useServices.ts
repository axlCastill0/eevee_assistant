import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, fetchServices, type ServicesResponse } from './api'

/**
 * Polls GET /services and keeps a short rolling history per service so tiles
 * can draw a heartbeat sparkline.
 *
 * The backend only reports current state, so the history is accumulated here
 * and therefore only covers "since this page loaded". That is labelled
 * honestly in the UI rather than implying persisted uptime data.
 */

export const POLL_MS = 3000

/** Samples kept per service. 60 x 3s = 3 minutes of trail. */
const HISTORY = 60

export interface Sample {
  t: number
  healthy: boolean
}

export interface ServicesState {
  data: ServicesResponse | null
  /** Set when the LAST poll failed. `data` keeps the last good values. */
  error: string | null
  /** True until the first poll settles, success or failure. */
  loading: boolean
  /** Wall-clock ms of the last successful poll. */
  updatedAt: number | null
  /** Round-trip of the last successful poll, ms. */
  latencyMs: number | null
  /** Consecutive failures. Drives the "stale" treatment in the UI. */
  failures: number
  history: Record<string, Sample[]>
  refresh: () => void
}

export function useServices(): ServicesState {
  const [data, setData] = useState<ServicesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<number | null>(null)
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [failures, setFailures] = useState(0)
  const [history, setHistory] = useState<Record<string, Sample[]>>({})

  // Avoids a setState on an unmounted component if a poll is in flight during
  // teardown (hot reload in dev, mostly).
  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const poll = useCallback(async () => {
    const started = performance.now()
    try {
      const res = await fetchServices()
      if (!alive.current) return

      setData(res)
      setError(null)
      setFailures(0)
      setLatencyMs(Math.round(performance.now() - started))
      setUpdatedAt(Date.now())

      const now = Date.now()
      setHistory((prev) => {
        const next: Record<string, Sample[]> = { ...prev }
        for (const svc of res.services) {
          const trail = next[svc.name] ?? []
          next[svc.name] = [...trail, { t: now, healthy: svc.healthy }].slice(-HISTORY)
        }
        return next
      })
    } catch (err) {
      if (!alive.current) return
      setError(err instanceof ApiError ? err.message : 'Unknown error')
      setFailures((n) => n + 1)
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void poll()
    const id = window.setInterval(() => void poll(), POLL_MS)
    return () => window.clearInterval(id)
  }, [poll])

  return {
    data,
    error,
    loading,
    updatedAt,
    latencyMs,
    failures,
    history,
    refresh: () => void poll(),
  }
}
