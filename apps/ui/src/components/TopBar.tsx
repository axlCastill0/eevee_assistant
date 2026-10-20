import { clockTime, longDate } from '../lib/format'
import type { VoiceState } from '../lib/useVoiceEvents'
import { PollRing } from './PollRing'
import { StatusIcons } from './StatusIcons'
import { VoicePill } from './VoicePill'
import './TopBar.css'

/** A status strip, not a control strip -- the one exception is the screen-off
 *  button. The theme control lives on the Settings page. */
export function TopBar({
  now,
  clockSynced,
  latencyMs,
  failures,
  loading,
  voice,
  timerCount,
  alarmSoon,
  onSleep,
}: {
  now: Date
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
}) {
  const { hm, seconds, meridiem } = clockTime(now)

  return (
    <header className="topbar">
      <div className="topbar__left">
        <div className="topbar__clock">
          <span className="topbar__time num">{hm}</span>
          {/* Seconds are deliberately smaller and dimmer: they move constantly
              and would otherwise pull the eye away from everything else. */}
          <span className="topbar__seconds num">{seconds}</span>
          {/* AM/PM is what makes 12-hour time unambiguous, so it has to be
              present, but it changes twice a day and never needs attention. */}
          <span className="topbar__meridiem">{meridiem}</span>
        </div>
        <div className="topbar__date">{clockSynced ? longDate(now) : 'waiting for clock sync'}</div>
      </div>

      <div className="topbar__right">
        {/* First in the row on purpose: it is the only element here that
            changes on a human timescale and needs to be found instantly. */}
        <VoicePill
          state={voice.state}
          transcript={voice.transcript}
          connected={voice.connected}
        />

        {/* Connection readout. Latency in monospace is the small detail that
            makes this feel like a dev tool rather than a consumer widget. */}
        <div className="topbar__conn">
          <PollRing active={!loading} stalled={failures > 0} />
          <div className="topbar__conn-text">
            <span className="topbar__conn-label">
              {failures > 0 ? `retrying (${failures})` : 'live'}
            </span>
            <span className="topbar__conn-latency mono">
              {latencyMs === null ? '--' : `${latencyMs}ms`}
            </span>
          </div>
        </div>

        <StatusIcons timerCount={timerCount} alarmSoon={alarmSoon} />

        {/* Screen off. Last in the row: it is the only control here that
            hides everything else. */}
        <button
          type="button"
          className="topbar__sleep"
          aria-label="Turn the screen off"
          onClick={onSleep}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
               strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 3v9" />
            <path d="M18.4 6.6a9 9 0 1 1-12.8 0" />
          </svg>
        </button>
      </div>
    </header>
  )
}
