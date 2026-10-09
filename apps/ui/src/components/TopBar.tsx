import { clockTime, longDate } from '../lib/format'
import type { ThemeMode } from '../lib/useTheme'
import type { VoiceState } from '../lib/useVoiceEvents'
import { PollRing } from './PollRing'
import { ThemeToggle } from './ThemeToggle'
import { VoicePill } from './VoicePill'
import './TopBar.css'

export function TopBar({
  now,
  mode,
  resolved,
  clockSynced,
  onChoose,
  latencyMs,
  failures,
  loading,
  voice,
}: {
  now: Date
  mode: ThemeMode
  resolved: 'light' | 'dark'
  clockSynced: boolean
  onChoose: (m: ThemeMode) => void
  latencyMs: number | null
  failures: number
  loading: boolean
  voice: { state: VoiceState; transcript: string | null; connected: boolean }
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

        <ThemeToggle
          mode={mode}
          resolved={resolved}
          clockSynced={clockSynced}
          onChoose={onChoose}
        />
      </div>
    </header>
  )
}
