/**
 * Live voice activity, over a WebSocket.
 *
 * WHY NOT POLLING
 *   Everything else on this dashboard is polled every 3s, which is correct for
 *   health. It is wrong here: the pill's job is to tell the user the microphone
 *   is open so they can start talking, and a 3s poll would show that an average
 *   of 1.5s late — after they have already started speaking into a pipeline
 *   that was not recording. This is the one piece of state that has to be
 *   pushed.
 *
 * The socket goes to /api/voice/events, which the ui's nginx proxies to the
 * backend while injecting X-API-Key, exactly like the REST calls. The browser
 * still never holds the key.
 */
import { useEffect, useRef, useState } from 'react'

export type VoiceState =
  | 'ready'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'offline'
  | 'unknown'

export interface VoiceEvent {
  seq: number
  state: VoiceState
  transcript: string | null
  speech: string | null
  at: number
}

const KNOWN: VoiceState[] = ['ready', 'listening', 'thinking', 'speaking', 'offline']

/** Reconnect backoff. Starts fast because the common case is a backend restart
 *  that is already over, and caps low because this kiosk runs for months and
 *  must not end up waiting minutes between attempts. */
const RETRY_MIN_MS = 500
const RETRY_MAX_MS = 5000

/** No frame at all for this long means the socket is dead even though the
 *  browser still thinks it is open — a suspended Pi network leaves exactly
 *  that. The server sends a keepalive every 20s, so 45s is two missed ones. */
const SILENCE_TIMEOUT_MS = 45_000

export interface VoiceFeed {
  /** Latest state, or 'unknown' before the first event arrives. */
  state: VoiceState
  /** Most recent transcript, kept until the next utterance replaces it. */
  transcript: string | null
  /** Sentence being spoken, on a 'speaking' event. */
  speech: string | null
  /** Monotonically increasing per event; the dialog uses it to tell a repeated
   *  answer from a re-render of the same one. */
  seq: number
  /** Whether the socket is currently up. False means the pill is showing the
   *  last thing it heard, which may be out of date. */
  connected: boolean
  /** True when the latest event is the hub's RETAINED one — the state as it
   *  was before this socket connected, replayed so the pill paints correctly
   *  on a kiosk reload. The pill wants it; the answer dialog must ignore it,
   *  or every reload would pop up whatever was last spoken, possibly hours
   *  ago. Found doing exactly that on 2026-10-08. */
  retained: boolean
  /** Set when the backend closed the socket for a bad key, which is a
   *  configuration problem rather than an outage and should not be retried
   *  silently forever. */
  rejected: boolean
}

export function useVoiceEvents(): VoiceFeed {
  const [feed, setFeed] = useState<VoiceFeed>({
    state: 'unknown',
    transcript: null,
    speech: null,
    seq: 0,
    connected: false,
    retained: false,
    rejected: false,
  })

  // Everything the reconnect loop needs lives in refs, so a state update does
  // not tear down and rebuild the socket.
  const socketRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(RETRY_MIN_MS)
  const timerRef = useRef<number | null>(null)
  const watchdogRef = useRef<number | null>(null)
  // The hub sends its retained event first on every connection, so this is
  // per-connection, not per-mount.
  const firstMessageRef = useRef(true)

  useEffect(() => {
    // Scoped to this effect run, NOT a ref. React 18 StrictMode mounts the
    // component twice in development, and a shared ref is cleared by the
    // second mount before the first socket's onclose has fired — so the dead
    // socket's handlers run against the live connection and cancel its
    // watchdog. A closure variable belongs to one connection attempt and
    // cannot be reset out from under it.
    let cancelled = false

    const clearTimers = () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
      if (watchdogRef.current !== null) window.clearTimeout(watchdogRef.current)
      timerRef.current = null
      watchdogRef.current = null
    }

    const armWatchdog = () => {
      if (watchdogRef.current !== null) window.clearTimeout(watchdogRef.current)
      watchdogRef.current = window.setTimeout(() => {
        // close() triggers onclose, which schedules the reconnect. Doing it
        // this way keeps one reconnect path instead of two.
        socketRef.current?.close()
      }, SILENCE_TIMEOUT_MS)
    }

    const connect = () => {
      if (cancelled) return

      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${scheme}://${window.location.host}/api/voice/events`)
      socketRef.current = ws

      ws.onopen = () => {
        if (cancelled) return
        firstMessageRef.current = true
        retryRef.current = RETRY_MIN_MS
        setFeed((f) => ({ ...f, connected: true, rejected: false }))
        armWatchdog()
      }

      ws.onmessage = (ev) => {
        if (cancelled) return
        armWatchdog()

        let msg: unknown
        try {
          msg = JSON.parse(ev.data as string)
        } catch {
          return
        }
        if (typeof msg !== 'object' || msg === null) return

        const data = msg as Partial<VoiceEvent> & { type?: string }
        if (data.type === 'ping') return // keepalive, carries no state

        const retained = firstMessageRef.current
        firstMessageRef.current = false

        const state = KNOWN.includes(data.state as VoiceState)
          ? (data.state as VoiceState)
          : 'unknown'

        setFeed((f) => ({
          ...f,
          state,
          seq: data.seq ?? f.seq,
          // Null means "this event does not carry one", not "clear it" — the
          // transcript must survive the speaking event that follows it.
          transcript: data.transcript ?? f.transcript,
          speech: data.speech ?? f.speech,
          connected: true,
          retained,
        }))
      }

      ws.onclose = (ev) => {
        if (cancelled) return
        clearTimers()

        // 1008 is the backend rejecting the API key. Retrying cannot fix a
        // mismatched secret, so surface it instead of flapping forever — but
        // keep retrying slowly in case nginx was restarted mid-deploy.
        const rejected = ev.code === 1008
        setFeed((f) => ({ ...f, connected: false, rejected }))

        timerRef.current = window.setTimeout(connect, retryRef.current)
        retryRef.current = Math.min(retryRef.current * 2, RETRY_MAX_MS)
      }

      // onerror always precedes onclose; the reconnect belongs in one place.
      ws.onerror = () => {}
    }

    connect()

    return () => {
      cancelled = true
      clearTimers()
      socketRef.current?.close()
    }
  }, [])

  return feed
}
