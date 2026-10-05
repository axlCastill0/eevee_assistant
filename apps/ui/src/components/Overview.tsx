import type { ServicesResponse } from '../lib/api'
import { StatusDot } from './StatusDot'
import './Overview.css'

/**
 * The headline tile: one sentence answering "is anything wrong".
 *
 * It reuses the backend's own `speech` string — the same text the voice
 * assistant says out loud. That is deliberate: the panel and the assistant
 * can never disagree about the system's state, because there is one place
 * that phrases it.
 */
export function Overview({
  data,
  error,
  loading,
}: {
  data: ServicesResponse | null
  error: string | null
  loading: boolean
}) {
  // Backend unreachable is itself a status, and the most important one — the
  // dashboard must say so rather than showing stale green.
  if (error && !data) {
    return (
      <section className="overview overview--down themed" style={{ '--i': 0 } as React.CSSProperties}>
        <div className="overview__row">
          <StatusDot tone="down" size={16} />
          <span className="overview__eyebrow">System</span>
        </div>
        <h1 className="overview__headline">Backend unreachable</h1>
        <p className="overview__sub mono">{error}</p>
      </section>
    )
  }

  if (loading && !data) {
    return (
      <section className="overview themed" style={{ '--i': 0 } as React.CSSProperties}>
        <div className="overview__row">
          <StatusDot tone="idle" size={16} pulse={false} />
          <span className="overview__eyebrow">System</span>
        </div>
        <h1 className="overview__headline overview__headline--muted">Connecting&hellip;</h1>
      </section>
    )
  }

  if (!data) return null

  const ok = data.all_healthy
  const down = data.services.filter((s) => !s.healthy)

  return (
    <section
      className={`overview ${ok ? 'overview--ok' : 'overview--down'} themed`}
      style={{ '--i': 0 } as React.CSSProperties}
    >
      <div className="overview__row">
        <StatusDot tone={ok ? 'ok' : 'down'} size={16} />
        <span className="overview__eyebrow">System</span>
        {/* Stale marker: data is on screen but the last poll failed. Showing
            the age is more honest than silently freezing. */}
        {error && <span className="overview__stale mono">stale &middot; {error}</span>}
      </div>

      <h1 className="overview__headline">{data.speech}</h1>

      <p className="overview__sub">
        {ok ? (
          <>
            {data.services.length} service{data.services.length === 1 ? '' : 's'} reporting
            healthy
          </>
        ) : (
          <>
            {down.length} of {data.services.length} service
            {data.services.length === 1 ? '' : 's'} need attention
          </>
        )}
      </p>
    </section>
  )
}
