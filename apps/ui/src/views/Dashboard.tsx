/**
 * The systems view — what used to be the whole dashboard.
 *
 * Lifted out of App.tsx unchanged when the sidebar arrived: App owns the
 * chrome (top bar, sidebar, voice dialog, screen veil) and each view owns its
 * own content and nothing else.
 */
import { ServiceTile } from '../components/ServiceTile'
import { Overview } from '../components/Overview'
import { agoLabel } from '../lib/format'
import type { ServicesResponse } from '../lib/api'
import type { Sample } from '../lib/useServices'

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
  return (
    <>
      <main className="app__grid">
        <Overview data={data} error={error} loading={loading} />

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

        {/* Placeholder so the grid reads as intentionally unfinished rather
            than broken while there are only two services. Remove once the
            row fills up. */}
        {data && data.services.length < 3 && (
          <div
            className="placeholder themed"
            style={{ '--i': data.services.length + 1 } as React.CSSProperties}
          >
            <span className="placeholder__plus" aria-hidden>
              +
            </span>
            <span className="placeholder__text">More systems land here</span>
          </div>
        )}
      </main>

      <footer className="app__footer">
        <span className="mono">eevee</span>
        <span className="app__footer-sep" aria-hidden />
        <span className="mono">updated {agoLabel(updatedAt)}</span>
        {data && (
          <>
            <span className="app__footer-sep" aria-hidden />
            <span className="mono">stale after {data.stale_after_s}s</span>
          </>
        )}
      </footer>
    </>
  )
}
