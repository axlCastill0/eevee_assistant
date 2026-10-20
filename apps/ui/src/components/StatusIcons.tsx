/**
 * Static status icons in the status line.
 *
 * Deliberately NOT countdowns. A ticking number up here would pull the eye
 * away from whatever page is open, every second, forever; the question these
 * answer is only "is something set?", and the dashboard answers "how long".
 *
 * They are also not buttons. Tapping a status to navigate is a hidden
 * affordance on a panel whose navigation is a permanent rail two inches to
 * the left.
 */
import { Icon } from './Term'
import './StatusIcons.css'

export function StatusIcons({
  timerCount,
  alarmSoon,
}: {
  timerCount: number
  alarmSoon: boolean
}) {
  if (timerCount === 0 && !alarmSoon) return null

  return (
    <div className="statusicons">
      {timerCount > 0 && (
        <span
          className="statusicons__item"
          title={`${timerCount} timer${timerCount === 1 ? '' : 's'} running`}
          aria-label={`${timerCount} timer${timerCount === 1 ? '' : 's'} running`}
        >
          <Icon name="timer" />
          {/* The count only appears when it is ambiguous. One timer needs no
              number; three do. */}
          {timerCount > 1 && <span className="statusicons__count num">{timerCount}</span>}
        </span>
      )}

      {alarmSoon && (
        <span
          className="statusicons__item statusicons__item--alarm"
          title="An alarm is set for the next 24 hours"
          aria-label="An alarm is set for the next 24 hours"
        >
          <Icon name="bell" />
        </span>
      )}
    </div>
  )
}
