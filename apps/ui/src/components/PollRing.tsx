import { POLL_MS } from '../lib/useServices'
import './PollRing.css'

const R = 9
const CIRC = 2 * Math.PI * R

/**
 * A ring that sweeps once per poll interval.
 *
 * Purely decorative but genuinely informative: it shows the dashboard is
 * still polling, so a frozen UI is immediately distinguishable from a quiet
 * one. The animation is CSS-driven and loops forever without React
 * re-rendering, which is the point — a progress bar driven by state would
 * re-render the tree 20 times a second.
 */
export function PollRing({ active, stalled }: { active: boolean; stalled: boolean }) {
  return (
    <svg
      className={`pollring${stalled ? ' is-stalled' : ''}`}
      viewBox="0 0 24 24"
      width="24"
      height="24"
      aria-hidden
    >
      <circle className="pollring__track" cx="12" cy="12" r={R} />
      <circle
        className="pollring__sweep"
        cx="12"
        cy="12"
        r={R}
        style={
          {
            '--circ': CIRC,
            strokeDasharray: CIRC,
            animationDuration: `${POLL_MS}ms`,
            animationPlayState: active ? 'running' : 'paused',
          } as React.CSSProperties
        }
      />
    </svg>
  )
}
