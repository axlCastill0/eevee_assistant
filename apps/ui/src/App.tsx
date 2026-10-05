import { useMemo, useState } from 'react'
import './App.css'
import { DetailSheet } from './components/DetailSheet'
import { Overview } from './components/Overview'
import { ServiceTile } from './components/ServiceTile'
import { TopBar } from './components/TopBar'
import { agoLabel } from './lib/format'
import { useClock } from './lib/useClock'
import { useServices } from './lib/useServices'
import { useTheme } from './lib/useTheme'

export default function App() {
  const now = useClock()
  const { mode, resolved, clockSynced, choose } = useTheme()
  const { data, error, loading, updatedAt, latencyMs, failures, history } = useServices()

  const [openName, setOpenName] = useState<string | null>(null)

  const open = useMemo(
    () => data?.services.find((s) => s.name === openName) ?? null,
    [data, openName],
  )

  // Close the sheet if its service disappears from the catalogue — otherwise
  // it would hang around showing values that no longer refresh.
  if (openName && data && !open) setOpenName(null)

  return (
    <div className="app">
      <TopBar
        now={now}
        mode={mode}
        resolved={resolved}
        clockSynced={clockSynced}
        onChoose={choose}
        latencyMs={latencyMs}
        failures={failures}
        loading={loading}
      />

      <main className="app__grid">
        <Overview data={data} error={error} loading={loading} />

        {data?.services.map((svc, i) => (
          <ServiceTile
            key={svc.name}
            service={svc}
            samples={history[svc.name] ?? []}
            staleAfterS={data.stale_after_s}
            index={i}
            onOpen={() => setOpenName(svc.name)}
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
        <span className="mono">
          updated {agoLabel(updatedAt)}
        </span>
        {data && (
          <>
            <span className="app__footer-sep" aria-hidden />
            <span className="mono">stale after {data.stale_after_s}s</span>
          </>
        )}
      </footer>

      {open && (
        <DetailSheet
          service={open}
          samples={history[open.name] ?? []}
          staleAfterS={data?.stale_after_s ?? 45}
          onClose={() => setOpenName(null)}
        />
      )}
    </div>
  )
}
