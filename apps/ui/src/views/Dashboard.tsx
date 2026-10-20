/**
 * Systems — the service report.
 *
 * Laid out as a log rather than as a grid of cards (2026-10-19): the question
 * this page answers is "is anything wrong", and a column of aligned verdicts
 * answers it in one downward glance where a grid made the eye hunt. Each row
 * is still the whole touch target, and tapping one opens the detail sheet.
 */
import { ServiceTile } from '../components/ServiceTile'
import { Overview } from '../components/Overview'
import { Pane } from '../components/Term'
import { agoLabel } from '../lib/format'
import type { ServicesResponse } from '../lib/api'
import type { Sample } from '../lib/useServices'
import './Systems.css'

export function Dashboard({
  data,
  error,
  loading,
  updatedAt,
  history,
  onOpen,
}: {
  data: ServicesResponse | null
  error: string | null
  loading: boolean
  updatedAt: number | null
  history: Record<string, Sample[]>
  onOpen: (name: string) => void
}) {
  const down = data?.services.filter((s) => !s.healthy).length ?? 0

  return (
    <main className="sys">
      <header className="sys__head">
        <span className="prompt" aria-hidden>
          ❯
        </span>
        <h1 className="sys__title">Systems</h1>
        <span className="caret" aria-hidden />
      </header>

      <Overview data={data} error={error} loading={loading} />

      <Pane
        title="services"
        icon="container"
        focus={down > 0}
        flush
        meta={
          data
            ? `${data.services.length - down}/${data.services.length} up`
            : loading
              ? 'polling'
              : '--'
        }
      >
        <div className="sys__rows">
          {data?.services.map((svc, i) => (
            <ServiceTile
              key={svc.name}
              service={svc}
              samples={history[svc.name] ?? []}
              staleAfterS={data.stale_after_s}
              index={i}
              onOpen={() => onOpen(svc.name)}
            />
          ))}

          {!data && (
            <p className="sys__waiting mono">
              {error ? 'no data: the backend is unreachable' : 'waiting for the first poll…'}
            </p>
          )}
        </div>
      </Pane>

      <footer className="sys__footer mono">
        <span>updated {agoLabel(updatedAt)}</span>
        <span className="sys__footer-sep" aria-hidden>
          │
        </span>
        <span>stale after {data?.stale_after_s ?? '--'}s</span>
        <span className="sys__footer-sep" aria-hidden>
          │
        </span>
        <span>eevee</span>
      </footer>
    </main>
  )
}
