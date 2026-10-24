import { clockTime, longDate } from '../lib/format'
import type { Route } from '../lib/useRoute'
import type { VoiceState } from '../lib/useVoiceEvents'
import { PollRing } from './PollRing'
import { StatusIcons } from './StatusIcons'
import { Icon } from './Term'
import { VoicePill } from './VoicePill'
import './TopBar.css'

/** The status line.
 *
 *  A status strip, not a control strip -- the one exception is the screen-off
 *  button. The theme control lives on the Settings page.
 *
 *  Segments are separated by a literal │, as a multiplexer's status-right
 *  would be. The prompt line under the clock says which window you are in,
 *  which is the only place that information appears in words. */
export function TopBar({
  now,
  route,
  clockSynced,
  latencyMs,
  failures,
  loading,
  voice,
  timerCount,
  alarmSoon,
  onSleep,
  screenLocked,
  onLock,
}: {
  now: Date
  route: Route
  clockSynced: boolean
  latencyMs: number | null
  failures: number
  loading: boolean
  voice: { state: VoiceState; transcript: string | null; connected: boolean }
  /** How many timers are counting down. Zero hides the icon entirely. */
  timerCount: number
  /** An alarm is set to go off within 24 hours. */
  alarmSoon: boolean
  onSleep: () => void
  /** The screen is being held awake against the idle timer. */
  screenLocked: boolean
  onLock: (locked: boolean) => void
}) {
  const { hm, seconds, meridiem } = clockTime(now)

  return (
    <header className="statusline themed">
      <div className="statusline__left">
        <div className="statusline__clock">
          <span className="statusline__time num">{hm}</span>
          {/* Seconds are smaller and dimmer: they move constantly and would
              otherwise pull the eye away from everything else. */}
          <span className="statusline__seconds num">{seconds}</span>
          <span className="statusline__meridiem">{meridiem}</span>
        </div>

        <div className="statusline__prompt">
          <span className="statusline__user">eevee@panel</span>
          <span className="statusline__path">:~/{route}</span>
          <span className="statusline__sep" aria-hidden>
            │
          </span>
          <span className="statusline__date">
            {clockSynced ? longDate(now) : 'waiting for clock sync'}
          </span>
        </div>
      </div>

      <div className="statusline__right">
        {/* First in the row on purpose: the only element here that changes on
            a human timescale and needs to be found instantly. */}
        <VoicePill
          state={voice.state}
          transcript={voice.transcript}
          connected={voice.connected}
        />

        <span className="statusline__sep" aria-hidden>
          │
        </span>

        <div className="statusline__conn">
          <PollRing active={!loading} stalled={failures > 0} />
          <span className="statusline__conn-label">
            {failures > 0 ? `retry ${failures}` : 'live'}
          </span>
          <span className="statusline__conn-latency num">
            {latencyMs === null ? '--' : `${latencyMs}ms`}
          </span>
        </div>

        <StatusIcons timerCount={timerCount} alarmSoon={alarmSoon} />

        <span className="statusline__sep" aria-hidden>
          │
        </span>

        {/* The screen control: one pill, two halves (USER 2026-10-24).
            They belong together because they are the same subject said two
            ways -- "keep it on" and "turn it off" -- and because the left
            half is the reason the right one is unavailable.

            Last in the row: the only controls here that hide everything
            else, and a thumb reaching the corner should not pass over the
            status icons on the way. */}
        <div className="screenpill" role="group" aria-label="Screen">
          <button
            type="button"
            className={`screenpill__seg${screenLocked ? ' is-on' : ''}`}
            aria-pressed={screenLocked}
            aria-label={
              screenLocked
                ? 'Let the screen turn itself off again'
                : 'Keep the screen on'
            }
            onClick={() => onLock(!screenLocked)}
          >
            <Icon name="lock" />
          </button>

          <button
            type="button"
            className="screenpill__seg screenpill__seg--power"
            /* Not hidden, DISABLED: the lock beside it is the explanation,
               and a control that vanishes teaches nothing. */
            disabled={screenLocked}
            aria-label={
              screenLocked
                ? 'Screen off — unavailable while the screen is held on'
                : 'Turn the screen off'
            }
            onClick={onSleep}
          >
            <Icon name="power" />
          </button>
        </div>
      </div>
    </header>
  )
}
