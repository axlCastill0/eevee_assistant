import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import { DetailSheet } from './components/DetailSheet'
import { RingingBanner } from './components/RingingBanner'
import { ScreenVeil } from './components/ScreenVeil'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { VoiceDialog } from './components/VoiceDialog'
import { setScreen, stopAlarm, stopRingingTimers } from './lib/api'
import { useClock } from './lib/useClock'
import { useClockState } from './lib/useClockState'
import { useIdle } from './lib/useIdle'
import { useRoute } from './lib/useRoute'
import { useServices } from './lib/useServices'
import { useTheme } from './lib/useTheme'
import { useVoiceEvents } from './lib/useVoiceEvents'
import { Alarms } from './views/Alarms'
import { Dashboard } from './views/Dashboard'
import { Home } from './views/Home'
import { NowPlaying } from './views/NowPlaying'
import { Settings } from './views/Settings'
import { Timers } from './views/Timers'
import { Wake } from './views/Wake'

export default function App() {
  const now = useClock()
  const route = useRoute()
  const { mode, clockSynced, choose } = useTheme()
  const { data, error, loading, updatedAt, latencyMs, failures, history } = useServices()
  const voice = useVoiceEvents()

  // Polled by the shell, not by a view: an alarm has to ring whatever page is
  // on screen, and the top bar's status icons need the same data.
  const clock = useClockState()

  const [openName, setOpenName] = useState<string | null>(null)
  const [screenOff, setScreenOff] = useState(false)

  // Stable identities: RingingBanner keys its audio effect on what it is
  // given, and a fresh arrow each render restarts the sound every poll.
  const { refresh: refreshClock } = clock
  const stopTimers = useCallback(
    () => void stopRingingTimers().then(refreshClock),
    [refreshClock],
  )
  const dismissAlarm = useCallback(
    () => void stopAlarm().then(refreshClock),
    [refreshClock],
  )

  // Local state for an instant veil; the POST is what the host agent follows.
  const sleepScreen = useCallback(
    (source: string) => {
      setScreenOff(true)
      void setScreen(false, source).then(refreshClock)
    },
    [refreshClock],
  )

  const wakeScreen = useCallback(() => {
    setScreenOff(false)
    void setScreen(true, 'touch').then(refreshClock)
  }, [refreshClock])

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

  // Follow the backend, so a browser that missed the WebSocket command (or
  // was opened afterwards) still agrees with the panel.
  const serverScreenOn = clock.data?.screen.on
  useEffect(() => {
    if (serverScreenOn !== undefined) setScreenOff(!serverScreenOn)
  }, [serverScreenOn])

  // Idle blank, per Settings. Zero disables it.
  const timeoutMin = Number(clock.data?.settings.screen_timeout_min ?? '0')
  const idleMs = Number.isFinite(timeoutMin) && timeoutMin > 0 ? timeoutMin * 60_000 : 0
  const idle = useIdle(idleMs)
  useEffect(() => {
    if (idle && !screenOff) sleepScreen('idle')
  }, [idle, screenOff, sleepScreen])

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
      <Sidebar route={route} />

      <div className="app__main">
        {/* The top bar is chrome on every view EXCEPT music, which is a
            full-bleed display surface -- the clock and the connection
            readout are noise in front of an album cover (USER DECISION
            2026-10-16). The sidebar stays, so there is always a way out. */}
        {route !== 'music' && (
          <TopBar
            now={now}
            clockSynced={clockSynced}
            latencyMs={latencyMs}
            failures={failures}
            loading={loading}
            voice={{
              state: voiceState,
              transcript: voice.transcript,
              connected: voice.connected,
            }}
            timerCount={clock.timers.filter((t) => !t.ringing).length}
            alarmSoon={clock.alarmSoon}
            onSleep={() => sleepScreen('button')}
          />
        )}

        {route === 'music' && (
          /* `active` gates the polling, so the view stops asking the backend
             for playback the moment it is not on screen. Mounting is enough
             to start it; unmounting stops it. */
          <NowPlaying active />
        )}

        {/* The launcher. Timers and alarms are apps behind it now, each with
            the whole screen -- which is what let both grow controls a finger
            can actually use (USER DECISION 2026-10-16). */}
        {route === 'dashboard' && (
          <Home timers={clock.timers} alarms={clock.data?.alarms.alarms ?? []} />
        )}

        {route === 'timers' && (
          <Timers timers={clock.timers} onChanged={clock.refresh} />
        )}

        {route === 'alarms' && (
          <Alarms alarms={clock.data?.alarms.alarms ?? []} onChanged={clock.refresh} />
        )}

        {route === 'wake' && <Wake />}

        {route === 'settings' && (
          <Settings
            settings={clock.data?.settings ?? null}
            mode={mode}
            onChooseTheme={choose}
            onChanged={clock.refresh}
          />
        )}

        {route === 'systems' && (
          <Dashboard
            data={data}
            error={error}
            loading={loading}
            updatedAt={updatedAt}
            history={history}
            onOpen={setOpenName}
          />
        )}
      </div>

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

      {/* Rendered by the shell so it is reachable from every page, including
          the full-bleed music view. */}
      <RingingBanner
        timers={clock.ringingTimers}
        alarm={clock.ringingAlarm}
        timerSound={clock.data?.settings.timer_sound ?? ''}
        alarmSound={clock.data?.settings.alarm_sound ?? ''}
        onStopTimers={stopTimers}
        onStopAlarm={dismissAlarm}
      />

      <ScreenVeil on={screenOff} onDismiss={wakeScreen} />

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
