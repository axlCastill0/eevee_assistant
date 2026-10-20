import type { ServicesResponse } from '../lib/api'
import { Pane, Verdict } from './Term'
import './Overview.css'

/**
 * The headline pane: one sentence answering "is anything wrong".
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
      <Pane title="system" icon="pulse" focus meta="no response">
        <div className="ov">
          <Verdict tone="down" />
          <h2 className="ov__headline">Backend unreachable</h2>
          <p className="ov__sub mono">{error}</p>
        </div>
      </Pane>
    )
  }

  if (loading && !data) {
    return (
      <Pane title="system" icon="pulse" meta="polling">
        <div className="ov">
          <Verdict tone="idle" />
          <h2 className="ov__headline is-muted">Connecting&hellip;</h2>
        </div>
      </Pane>
    )
  }

  if (!data) return null

  const ok = data.all_healthy
  const down = data.services.filter((s) => !s.healthy)

  return (
    <Pane
      title="system"
      icon="pulse"
      focus={!ok}
      /* Stale marker: data is on screen but the last poll failed. Showing it
         is more honest than silently freezing. */
      meta={error ? 'stale' : `stale after ${data.stale_after_s}s`}
    >
      <div className="ov">
        <Verdict tone={ok ? 'ok' : 'down'} />
        <h2 className="ov__headline">{data.speech}</h2>
        <p className="ov__sub mono">
          {ok
            ? `${data.services.length} service${data.services.length === 1 ? '' : 's'} reporting healthy`
            : `${down.length} of ${data.services.length} service${data.services.length === 1 ? '' : 's'} need attention`}
          {error && ` · last poll failed: ${error}`}
        </p>
      </div>
    </Pane>
  )
}
