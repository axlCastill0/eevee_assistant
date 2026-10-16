/**
 * Settings — three, and no more than three.
 *
 * Two are server-side (which sound a timer and an alarm end with) and one is
 * not: the theme stays in this browser's localStorage, because a theme
 * belongs to a display rather than to the house. A phone opening the
 * dashboard should be able to be light while the wall panel is dark, and the
 * voice command "dark mode" writes to the same local store. See
 * backend/settings.py for the full argument.
 */
import { useState } from 'react'
import { updateSettings, type ClockState } from '../lib/api'
import type { ThemeMode } from '../lib/useTheme'
import './Settings.css'

const THEMES: { id: ThemeMode; label: string }[] = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'auto', label: 'Auto' },
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

  const save = (values: { timer_sound?: string; alarm_sound?: string }) => {
    setError(null)
    void updateSettings(values).then(onChanged, (err) =>
      setError(err instanceof Error ? err.message : 'Could not save'),
    )
  }

  const sounds = settings?.sounds ?? []

  return (
    <main className="settings">
      <h2 className="settings__heading">Settings</h2>

      <SoundSetting
        label="Timer end sound"
        hint="Plays when a countdown reaches zero."
        value={settings?.timer_sound ?? ''}
        sounds={sounds}
        onChange={(file) => save({ timer_sound: file })}
      />

      <SoundSetting
        label="Alarm end sound"
        hint="Plays when a weekday alarm goes off."
        value={settings?.alarm_sound ?? ''}
        sounds={sounds}
        onChange={(file) => save({ alarm_sound: file })}
      />

      <div className="settings__row">
        <div className="settings__label">
          Theme
          <span className="settings__hint">
            This screen only — each display remembers its own.
          </span>
        </div>
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

      {sounds.length === 0 && (
        <p className="settings__note">
          No sound files found in <code>{settings?.media_dir ?? 'the media folder'}</code>.
          Drop .mp3 files into <code>media/</code> at the repo root on the Pi — they
          appear here without a rebuild.
        </p>
      )}

      {error && <p className="settings__error">{error}</p>}
    </main>
  )
}

function SoundSetting({
  label,
  hint,
  value,
  sounds,
  onChange,
}: {
  label: string
  hint: string
  value: string
  sounds: ClockState['settings']['sounds']
  onChange: (file: string) => void
}) {
  return (
    <div className="settings__row">
      <div className="settings__label">
        {label}
        <span className="settings__hint">{hint}</span>
      </div>

      {/* A native <select> on purpose: Chromium renders it as a touch-friendly
          list on its own, and a hand-rolled dropdown would need scroll,
          focus trapping and dismissal logic to match it. */}
      <select
        className="settings__select"
        value={value}
        disabled={sounds.length === 0}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">None</option>
        {sounds.map((sound) => (
          <option key={sound.file} value={sound.file}>
            {sound.label}
          </option>
        ))}
      </select>
    </div>
  )
}
