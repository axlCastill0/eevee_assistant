/**
 * Settings — four keys, and no more than four.
 *
 * Laid out as a config file: each row shows the KEY the value is stored
 * under, not a sentence. On a panel whose whole language is a terminal, the
 * real key is both more honest and more useful -- `screen_timeout_min` is
 * what you grep for in settings.py when something misbehaves.
 *
 * Three keys are server-side; the theme is not. A theme belongs to a display
 * rather than to the house, so it stays in this browser's localStorage: a
 * phone opening the dashboard can be light while the wall panel is dark, and
 * the voice command "dark mode" writes to the same local store. See
 * backend/settings.py for the full argument.
 */
import { useState } from 'react'
import { Pane, Rule } from '../components/Term'
import { updateSettings, type ClockState } from '../lib/api'
import type { ThemeMode } from '../lib/useTheme'
import './Settings.css'

/** Minutes. 0 is "never". */
const TIMEOUTS = [0, 2, 5, 10, 15, 30, 60]

const THEMES: { id: ThemeMode; label: string }[] = [
  { id: 'light', label: 'light' },
  { id: 'dark', label: 'dark' },
  { id: 'auto', label: 'auto' },
]

export function Settings({
  settings,
  mode,
  onChooseTheme,
  onChanged,
}: {
  settings: ClockState['settings'] | null
  mode: ThemeMode
  onChooseTheme: (m: ThemeMode) => void
  onChanged: () => void
}) {
  const [error, setError] = useState<string | null>(null)

  const save = (values: {
    timer_sound?: string
    alarm_sound?: string
    screen_timeout_min?: string
  }) => {
    setError(null)
    void updateSettings(values).then(onChanged, (err) =>
      setError(err instanceof Error ? err.message : 'Could not save'),
    )
  }

  const sounds = settings?.sounds ?? []

  return (
    <main className="settings">
      <header className="settings__head">
        <span className="prompt" aria-hidden>
          ❯
        </span>
        <h1 className="settings__title">Settings</h1>
        <span className="caret" aria-hidden />
      </header>

      <Rule label="eevee.conf" icon="settings" />

      <Pane title="sounds" icon="volume" meta={`${sounds.length} file${sounds.length === 1 ? '' : 's'}`}>
        <SoundSetting
          name="timer_sound"
          hint="plays when a countdown reaches zero"
          value={settings?.timer_sound ?? ''}
          sounds={sounds}
          onChange={(file) => save({ timer_sound: file })}
        />

        <SoundSetting
          name="alarm_sound"
          hint="plays when a weekday alarm goes off"
          value={settings?.alarm_sound ?? ''}
          sounds={sounds}
          onChange={(file) => save({ alarm_sound: file })}
        />

        {sounds.length === 0 && (
          <p className="settings__note">
            No sound files in <code>{settings?.media_dir ?? 'the media folder'}</code>.
            Drop .mp3 files into <code>media/</code> at the repo root on the Pi — they
            appear here without a rebuild.
          </p>
        )}
      </Pane>

      <Pane title="display" icon="screen">
        <div className="settings__row">
          <div className="settings__label">
            <span className="settings__key">screen_timeout_min</span>
            <span className="settings__hint">
              no touch for this long and the panel blanks; the backlight goes
              with it if the screen agent is running
            </span>
          </div>
          <span className="leader" aria-hidden />
          <select
            className="settings__select"
            value={settings?.screen_timeout_min ?? '0'}
            onChange={(e) => save({ screen_timeout_min: e.target.value })}
          >
            {TIMEOUTS.map((minutes) => (
              <option key={minutes} value={String(minutes)}>
                {minutes === 0 ? 'never' : `${minutes} min`}
              </option>
            ))}
          </select>
        </div>

        <div className="settings__row">
          <div className="settings__label">
            <span className="settings__key">theme</span>
            <span className="settings__hint">this screen only — each display remembers its own</span>
          </div>
          <span className="leader" aria-hidden />
          <div className="settings__themes">
            {THEMES.map((theme) => (
              <button
                key={theme.id}
                type="button"
                className={`settings__theme${mode === theme.id ? ' is-active' : ''}`}
                aria-pressed={mode === theme.id}
                onClick={() => onChooseTheme(theme.id)}
              >
                {theme.label}
              </button>
            ))}
          </div>
        </div>
      </Pane>

      {error && <p className="settings__error mono">error: {error}</p>}
    </main>
  )
}

function SoundSetting({
  name,
  hint,
  value,
  sounds,
  onChange,
}: {
  name: string
  hint: string
  value: string
  sounds: ClockState['settings']['sounds']
  onChange: (file: string) => void
}) {
  return (
    <div className="settings__row">
      <div className="settings__label">
        <span className="settings__key">{name}</span>
        <span className="settings__hint">{hint}</span>
      </div>

      <span className="leader" aria-hidden />

      {/* A native <select> on purpose: Chromium renders it as a touch-friendly
          list on its own, and a hand-rolled dropdown would need scroll, focus
          trapping and dismissal logic to match it. */}
      <select
        className="settings__select"
        value={value}
        disabled={sounds.length === 0}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">none</option>
        {sounds.map((sound) => (
          <option key={sound.file} value={sound.file}>
            {sound.label}
          </option>
        ))}
      </select>
    </div>
  )
}
