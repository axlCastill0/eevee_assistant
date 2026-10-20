/**
 * Home — the wake-on-LAN app.
 *
 * ONE MACHINE, ONE BUTTON (USER DECISION 2026-10-16)
 *   Configured on the backend in `.env` (WOL_MAC / WOL_NAME / WOL_HOST),
 *   because there is no keyboard on this panel and a MAC address is set
 *   once. Nothing here can change the target; this view sends the packet and
 *   reports what happened.
 *
 * WHY THE POLL SPEEDS UP AFTER A WAKE
 *   A magic packet is never acknowledged — the only way to know whether the
 *   PC came up is the backend's TCP probe. Idle, that question is worth
 *   asking every few seconds. For the minute or two after you press Wake it
 *   is the only thing on screen anyone cares about, so the poll tightens and
 *   the card says it is waiting. It falls back on its own, so a panel left
 *   on this page does not probe hard forever.
 *
 * WHY "SENT" IS NOT "AWAKE"
 *   The button reports the packet leaving, which is all the backend can
 *   honestly claim. Only the status dot promises the machine is up, and it
 *   only promises it when a probe host is configured.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { AppHeader } from '../components/AppHeader'
import { Icon, Verdict } from '../components/Term'
import { fetchWake, sendWake, type WakeState } from '../lib/api'
import './Wake.css'

const IDLE_POLL_MS = 6000
const BUSY_POLL_MS = 2000
/** How long to keep watching after a wake before giving up on the dot. */
const WATCH_MS = 120_000

export function Wake() {
  const [data, setData] = useState<WakeState | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [wakingSince, setWakingSince] = useState<number | null>(null)

  const alive = useRef(true)
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const next = await fetchWake()
      if (alive.current) setData(next)
    } catch {
      // The TopBar already reports an unreachable backend; this card keeps
      // whatever it last knew rather than flickering to "not configured",
      // which would read as a broken .env.
    }
  }, [])

  const waiting = wakingSince !== null

  useEffect(() => {
    void refresh()
    const id = window.setInterval(
      () => void refresh(),
      waiting ? BUSY_POLL_MS : IDLE_POLL_MS,
    )
    return () => window.clearInterval(id)
  }, [refresh, waiting])

  // Stop watching once it answers, or once it has clearly not. Both end the
  // tightened poll; only the first is good news.
  useEffect(() => {
    if (wakingSince === null) return
    if (data?.online) {
      setWakingSince(null)
      setNotice(`${data.name} is up.`)
      return
    }
    const id = window.setTimeout(
      () => setWakingSince(null),
      Math.max(0, WATCH_MS - (Date.now() - wakingSince)),
    )
    return () => window.clearTimeout(id)
  }, [wakingSince, data])

  const wake = async () => {
    setNotice(null)
    try {
      const result = await sendWake()
      if (!alive.current) return
      setData(result)
      setNotice(result.detail)
      // Only watch when there is something that can answer.
      if (result.sent && result.probe_host) setWakingSince(Date.now())
    } catch {
      setNotice('The backend could not be reached.')
    }
  }

  const status = !data?.configured
    ? 'unconfigured'
    : waiting
      ? 'waking'
      : data.online === null
        ? 'unknown'
        : data.online
          ? 'online'
          : 'offline'

  const STATUS_TEXT: Record<string, string> = {
    unconfigured: 'no machine configured',
    waking: 'waiting for it to come up',
    unknown: 'status unknown',
    online: 'online',
    offline: 'offline',
  }

  return (
    <main className="wake">
      <AppHeader
        title="Home"
        subtitle={data?.configured ? data.name : 'wake on LAN'}
      />

      <section className={`wakecard themed is-${status}`} aria-label="Wake target">
        <div className="wakecard__head">
          <Verdict
            tone={status === 'online' ? 'ok' : status === 'offline' ? 'down' : 'idle'}
            label={status === 'waking' ? 'WAIT' : undefined}
          />
          <div className="wakecard__id">
            <h2 className="wakecard__name">
              {data?.configured ? data.name : 'Not configured'}
            </h2>
            <p className="wakecard__status">{STATUS_TEXT[status]}</p>
          </div>
        </div>

        {data?.configured ? (
          <button
            type="button"
            className="wakecard__btn"
            /* Still pressable while waiting: a magic packet can be dropped by
               any switch on the way and pressing again is the correct thing
               to try. Disabling it here would hide the only remedy. */
            onClick={() => void wake()}
          >
            <Icon name="power" />
            <span>{waiting ? 'send again' : 'wake'}</span>
          </button>
        ) : (
          <p className="wakecard__hint">
            Set <span className="mono">WOL_MAC</span> (and{' '}
            <span className="mono">WOL_HOST</span> for the status dot) in{' '}
            <span className="mono">infra/docker/.env</span>, then recreate the
            backend.
          </p>
        )}

        {notice && (
          /* Keyed on the text so repeating an action replays the entrance
             rather than leaving a line that looks stale. */
          <p key={notice} className="wakecard__notice">
            {notice}
          </p>
        )}

        {data?.configured && (
          <dl className="wakecard__facts">
            <div>
              <dt>MAC</dt>
              <dd className="mono">{data.mac}</dd>
            </div>
            <div>
              <dt>Probe</dt>
              <dd className="mono">
                {data.probe_host
                  ? `${data.probe_host}:${(data.probe_ports ?? []).join(',') || '--'}`
                  : 'not set'}
              </dd>
            </div>
          </dl>
        )}
      </section>
    </main>
  )
}
