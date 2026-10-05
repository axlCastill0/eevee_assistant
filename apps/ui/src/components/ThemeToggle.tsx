import type { ReactElement } from 'react'
import type { ThemeMode } from '../lib/useTheme'
import { DAY_END, DAY_START } from '../lib/useTheme'
import './ThemeToggle.css'

// React 19 no longer publishes a global JSX namespace, so the element type is
// imported explicitly rather than written as JSX.Element.
const MODES: { id: ThemeMode; label: string; icon: ReactElement }[] = [
  {
    id: 'light',
    label: 'Light',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
        <path
          d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    id: 'dark',
    label: 'Dark',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M20 14.2A8.2 8.2 0 1 1 9.8 4a6.6 6.6 0 0 0 10.2 10.2Z"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    id: 'auto',
    label: 'Auto',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <circle cx="12" cy="12" r="8.2" stroke="currentColor" strokeWidth="1.8" />
        {/* Half-filled: the clearest glyph for "follows the clock". */}
        <path d="M12 3.8a8.2 8.2 0 0 1 0 16.4Z" fill="currentColor" />
      </svg>
    ),
  },
]

/**
 * Three-state segmented control.
 *
 * A single cycling button would be smaller, but on a touch panel the current
 * state has to be readable without pressing anything — so all three modes are
 * always visible and the active one is marked. The indicator slides between
 * segments via a transform, which keeps it on the compositor.
 */
export function ThemeToggle({
  mode,
  resolved,
  clockSynced,
  onChoose,
}: {
  mode: ThemeMode
  resolved: 'light' | 'dark'
  clockSynced: boolean
  onChoose: (m: ThemeMode) => void
}) {
  const index = MODES.findIndex((m) => m.id === mode)

  return (
    <div className="themetoggle">
      <div
        className="themetoggle__track themed"
        style={{ '--index': index } as React.CSSProperties}
      >
        <span className="themetoggle__indicator" aria-hidden />
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            className={`themetoggle__seg${mode === m.id ? ' is-active' : ''}`}
            onClick={() => onChoose(m.id)}
            aria-pressed={mode === m.id}
            aria-label={`${m.label} theme`}
          >
            <span className="themetoggle__icon">{m.icon}</span>
            <span className="themetoggle__label">{m.label}</span>
          </button>
        ))}
      </div>

      {/* In auto mode, say what it is doing and why. Without this the only
          feedback for "auto" is the theme itself, which is ambiguous at the
          boundary hours. */}
      {mode === 'auto' && (
        <div className="themetoggle__hint mono">
          {clockSynced ? (
            <>
              {resolved} &middot; {String(DAY_START).padStart(2, '0')}:00&ndash;
              {String(DAY_END).padStart(2, '0')}:00 light
            </>
          ) : (
            <span className="themetoggle__hint--warn">clock not synced &middot; holding dark</span>
          )}
        </div>
      )}
    </div>
  )
}
