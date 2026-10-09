import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { DetailSheet } from './components/DetailSheet'
import { Overview } from './components/Overview'
import { ServiceTile } from './components/ServiceTile'
import { ScreenVeil } from './components/ScreenVeil'
import { TopBar } from './components/TopBar'
import { VoiceDialog } from './components/VoiceDialog'
import { agoLabel } from './lib/format'
import { useClock } from './lib/useClock'
import { useServices } from './lib/useServices'
import { useTheme } from './lib/useTheme'
import { useVoiceEvents } from './lib/useVoiceEvents'

export default function App() {
  const now = useClock()
  const { mode, resolved, clockSynced, choose } = useTheme()
  const { data, error, loading, updatedAt, latencyMs, failures, history } = useServices()
  const voice = useVoiceEvents()

  const [openName, setOpenName] = useState<string | null>(null)
  const [screenOff, setScreenOff] = useState(false)

  // Commands from the assistant: theme changes and screen blanking. Keyed on
  // the command object's identity, which is fresh for every command, so
  // saying "dark mode" twice applies twice rather than being swallowed as an
  // unchanged prop.
  const command = voice.command
  useEffect(() => {
    if (!command) return

    switch (command.command) {
      case 'set_theme':
        if (command.value === 'light' || command.value === 'dark' || command.value === 'auto') {
          choose(command.value)
        }
        break
      case 'sleep_screen':
        setScreenOff(true)
        break
      case 'wake_screen':
        setScreenOff(false)
        break
      default:
        // An unrecognised command is a backend newer than this bundle. Ignore
        // it rather than guessing.
        break
    }
  }, [command, choose])

  // The event stream only reports what the pipeline SAYS it is doing, so a
  // pipeline that died mid-utterance would leave the pill stuck on green
  // forever. Heartbeat staleness is the authority on whether it is alive at
  // all, so a voice service the backend reports as down overrides the last
  // event. Same reasoning as "never checked in counts as down".
  const voiceDown =
    data?.services.some((s) => s.name === 'voice' && !s.healthy) ?? false
  const voiceState = voiceDown ? 'offline' : voice.state

  const open = useMemo(
    () => data?.services.find((s) => s.name === openName) ?? null,
    [data, openName],
  )

  // Close the sheet if its service disappears from the catalogue — otherwise
  // it would hang around showing values that no longer refresh.
  if (openName && data && !open) setOpenName(null)

  return (
    <div className="app">
      <TopBar
        now={now}
        mode={mode}
        resolved={resolved}
        clockSynced={clockSynced}
        onChoose={choose}
        latencyMs={latencyMs}
        failures={failures}
        loading={loading}
        voice={{
          state: voiceState,
          transcript: voice.transcript,
          connected: voice.connected,
        }}
      />

      <main className="app__grid">
        <Overview data={data} error={error} loading={loading} />

        {data?.services.map((svc, i) => (
          <ServiceTile
            key={svc.name}
            service={svc}
            samples={history[svc.name] ?? []}
            staleAfterS={data.stale_after_s}
            index={i}
            onOpen={() => setOpenName(svc.name)}
          />
        ))}

        {/* Placeholder so the grid reads as intentionally unfinished rather
            than broken while there are only two services. Remove once the
            row fills up. */}
        {data && data.services.length < 3 && (
          <div
            className="placeholder themed"
            style={{ '--i': data.services.length + 1 } as React.CSSProperties}
          >
            <span className="placeholder__plus" aria-hidden>
              +
            </span>
            <span className="placeholder__text">More systems land here</span>
          </div>
        )}
      </main>

      <footer className="app__footer">
        <span className="mono">eevee</span>
        <span className="app__footer-sep" aria-hidden />
        <span className="mono">
          updated {agoLabel(updatedAt)}
        </span>
        {data && (
          <>
            <span className="app__footer-sep" aria-hidden />
            <span className="mono">stale after {data.stale_after_s}s</span>
          </>
        )}
      </footer>

      {/* Raw event state, NOT voiceState: the offline override is driven by
          heartbeat staleness, and an answer arriving is itself proof the
          pipeline is alive. Using the override here would suppress exactly the
          dialog the user is waiting on if a beat happened to be late. */}
      <VoiceDialog
        speech={voice.speech}
        seq={voice.seq}
        speaking={voice.state === 'speaking'}
        retained={voice.retained}
      />

      <ScreenVeil on={screenOff} onDismiss={() => setScreenOff(false)} />

      {open && (
        <DetailSheet
          service={open}
          samples={history[open.name] ?? []}
          staleAfterS={data?.stale_after_s ?? 45}
          onClose={() => setOpenName(null)}
        />
      )}
    </div>
  )
}
