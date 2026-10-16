/**
 * The header of an app opened from the launcher.
 *
 * WHY A BACK BUTTON AT ALL, WHEN THE SIDEBAR IS RIGHT THERE
 *   The sidebar's Dashboard entry does go home, but it is a 72px rail on the
 *   far left and these apps are reached by tapping a card in the middle of
 *   the screen. A back control where the eye already is costs one tile of
 *   space and saves a cross-screen reach every time.
 *
 *   It is `goHome`, not history.back(): the kiosk can be pointed straight at
 *   `#/timers`, where there is no previous entry.
 */
import { goHome } from '../lib/useRoute'
import './AppHeader.css'

export function AppHeader({
  title,
  /** One line under the title: what this app currently amounts to. */
  subtitle,
  /** Right-hand slot, for the one action that belongs to the whole app. */
  action,
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
}) {
  return (
    <header className="appheader">
      <button
        type="button"
        className="appheader__back"
        aria-label="Back to the dashboard"
        onClick={goHome}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M14.5 5 8 12l6.5 7" />
        </svg>
      </button>

      <div className="appheader__text">
        <h1 className="appheader__title">{title}</h1>
        {subtitle && <p className="appheader__subtitle">{subtitle}</p>}
      </div>

      {action && <div className="appheader__action">{action}</div>}
    </header>
  )
}
