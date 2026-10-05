import type { ServiceEntry } from '../lib/api'
import { duration, serviceLabel } from '../lib/format'
import type { Sample } from '../lib/useServices'
import { Sparkline } from './Sparkline'
import { StatusDot } from './StatusDot'
import './ServiceTile.css'

/**
 * One service. Tap opens the detail sheet.
 *
 * The whole tile is the touch target rather than a button inside it — on a
 * finger-driven panel, small affordances inside a large card are a mis-tap
 * waiting to happen.
 */
export function ServiceTile({
  service,
  samples,
  staleAfterS,
  index,
  onOpen,
}: {
  service: ServiceEntry
  samples: Sample[]
  staleAfterS: number
  index: number
  onOpen: () => void
}) {
  const ok = service.healthy
  const age = service.last_seen_s_ago

  // Fraction of the stale window consumed. Approaching 1 means a heartbeat is
  // overdue and the service is about to be marked down, which is worth seeing
  // before it happens.
  const pressure = age === null ? 1 : Math.min(1, age / staleAfterS)
  const nearStale = ok && pressure > 0.6

  return (
    <button
      type="button"
      className={`tile ${ok ? 'tile--ok' : 'tile--down'} themed`}
      style={{ '--i': index + 1 } as React.CSSProperties}
      onClick={onOpen}
      aria-label={`${serviceLabel(service.name)}: ${service.detail}`}
    >
      <div className="tile__head">
        <StatusDot tone={ok ? (nearStale ? 'warn' : 'ok') : 'down'} size={12} />
        <span className="tile__name">{serviceLabel(service.name)}</span>
        <svg className="tile__chev" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M9 5l7 7-7 7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <div className="tile__body">
        <span className={`tile__state ${ok ? '' : 'tile__state--down'}`}>
          {ok ? 'Healthy' : 'Down'}
        </span>
        <span className="tile__detail">{service.detail}</span>
      </div>

      <div className="tile__metrics">
        <div className="tile__metric">
          <span className="tile__metric-label">Last seen</span>
          <span className="tile__metric-value num">{duration(age)}</span>
        </div>
        <div className="tile__metric">
          <span className="tile__metric-label">Stale at</span>
          <span className="tile__metric-value num">{duration(staleAfterS)}</span>
        </div>
      </div>

      <div className="tile__spark">
        <Sparkline samples={samples} />
        <span className="tile__spark-label">since load</span>
      </div>

      {/* Heartbeat pressure bar: fills as the last heartbeat ages. Scales via
          transform so it animates on the compositor. */}
      <div className="tile__pressure" aria-hidden>
        <span
          className={`tile__pressure-fill${nearStale ? ' is-warn' : ''}`}
          style={{ transform: `scaleX(${pressure})` }}
        />
      </div>
    </button>
  )
}
