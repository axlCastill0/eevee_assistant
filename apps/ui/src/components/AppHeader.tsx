/**
 * The header of an app opened from the launcher.
 *
 * WHY A BACK BUTTON AT ALL, WHEN THE RAIL IS RIGHT THERE
 *   The rail's Dashboard entry does go home, but it is a narrow strip on the
 *   far left and these apps are reached by tapping a card in the middle of
 *   the screen. A back control where the eye already is costs one tile of
 *   space and saves a cross-screen reach every time.
 *
 *   It is `goHome`, not history.back(): the kiosk can be pointed straight at
 *   `#/timers`, where there is no previous entry.
 */
import { goHome } from '../lib/useRoute'
import { Icon } from './Term'
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
        <Icon name="left" />
      </button>

      <div className="appheader__text">
        <h1 className="appheader__title">
          <span className="prompt" aria-hidden>
            ❯{' '}
          </span>
          {title}
        </h1>
        {subtitle && <p className="appheader__subtitle mono">{subtitle}</p>}
      </div>

      {action && <div className="appheader__action">{action}</div>}
    </header>
  )
}
