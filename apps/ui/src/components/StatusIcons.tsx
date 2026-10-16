/**
 * Static status icons in the top bar.
 *
 * Deliberately NOT countdowns. A ticking number up here would pull the eye
 * away from whatever page is open, every second, forever; the question these
 * answer is only "is something set?", and the Dashboard answers "how long".
 *
 * They are also not buttons. Tapping a status to navigate is a hidden
 * affordance on a panel whose navigation is a permanent rail two inches to
 * the left.
 */
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
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <circle cx="12" cy="13" r="8" />
            <path d="M12 9v4l2.5 2M9 2h6" />
          </svg>
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
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M18 8.5a6 6 0 1 0-12 0c0 6-2 7.5-2 7.5h16s-2-1.5-2-7.5Z" />
            <path d="M10.5 19.5a2 2 0 0 0 3 0" />
          </svg>
        </span>
      )}
    </div>
  )
}
