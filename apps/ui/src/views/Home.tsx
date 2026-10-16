/**
 * Home — the launcher.
 *
 * WHAT CHANGED AND WHY (USER DECISION 2026-10-16)
 *   The home route used to BE the timers-and-alarms page. It is now a
 *   springboard: a glance strip of live state across the top, and a grid of
 *   app tiles under it. Timers and alarms became apps of their own with the
 *   whole screen each, which is what let both of them grow controls that
 *   actually fit a finger.
 *
 * THE GLANCE STRIP IS CONDITIONAL
 *   A card appears only when it has something to say: timers while any exist,
 *   the next alarm only while one is enabled, now playing only while
 *   something is actually playing. Weather is the exception and is always
 *   there -- it is the one thing on this screen that is worth reading when
 *   nothing at all is happening, and a home screen that empties to nothing
 *   reads as broken.
 *
 *   An empty strip is therefore possible but never likely, and the grid below
 *   does not move when a card comes or goes: the strip holds its height.
 *
 * TAP TARGETS
 *   Every card is the target, not a button inside it, and each one leads to
 *   the app it is summarising. Weather leads nowhere yet, so it is a div
 *   rather than a button -- a tile that looks pressable and does nothing is
 *   worse than one that plainly does not.
 */
import type { AlarmEntry, TimerEntry } from '../lib/api'
import { artUrl } from '../lib/api'
import { duration } from '../lib/format'
import { navigate, type Route } from '../lib/useRoute'
import { useSpotify } from '../lib/useSpotify'
import { countdown } from '../lib/useClockState'
import { useWeather, weatherIcon } from '../lib/useWeather'
import { WeatherGlyph } from '../components/WeatherGlyph'
import './Home.css'

export function Home({
  timers,
  alarms,
}: {
  timers: TimerEntry[]
  alarms: AlarmEntry[]
}) {
  const weather = useWeather()
  // Mounted here, so the poll stops the moment you leave the launcher. The
  // controls are not used -- this card is a readout and a shortcut.
  const spotify = useSpotify(true)

  const running = timers.filter((t) => !t.ringing && !t.paused)
  const soonest = running[0] ?? timers[0] ?? null

  // The soonest enabled slot. `next_fire_in_s` is null on a disabled one, so
  // this is also the "is anything set at all" test.
  const nextAlarm = alarms
    .filter((a) => a.enabled && a.next_fire_in_s !== null)
    .sort((a, b) => (a.next_fire_in_s ?? 0) - (b.next_fire_in_s ?? 0))[0]

  const playing =
    spotify.data?.status === 'ok' && spotify.data.is_playing
      ? spotify.data.item
      : undefined

  // Index drives the entrance stagger. Counted as cards are emitted so the
  // sequence has no gaps when a card is absent.
  let i = 0

  return (
    <main className="home">
      {/* Two slow-moving blobs. Decorative, transform-only, and behind
          everything -- the one piece of pure atmosphere on the panel. */}
      <div className="home__aura" aria-hidden>
        <span className="home__blob home__blob--a" />
        <span className="home__blob home__blob--b" />
      </div>

      <section className="home__glance" aria-label="At a glance">
        {soonest && (
          <GlanceCard
            index={i++}
            tone="accent"
            onClick={() => navigate('timers')}
            label={
              timers.length > 1 ? `Timers · ${timers.length}` : 'Timer'
            }
            value={
              soonest.ringing ? 'done' : countdown(soonest.remaining_s)
            }
            detail={
              soonest.ringing
                ? 'tap to clear'
                : soonest.paused
                  ? `${soonest.label} · paused`
                  : soonest.label
            }
            urgent={soonest.ringing || (!soonest.paused && soonest.remaining_s <= 10)}
            progress={
              soonest.duration_s > 0 && !soonest.ringing
                ? 1 - soonest.remaining_s / soonest.duration_s
                : undefined
            }
          />
        )}

        {nextAlarm && (
          <GlanceCard
            index={i++}
            tone="info"
            onClick={() => navigate('alarms')}
            label="Next alarm"
            value={nextAlarm.label}
            detail={`${nextAlarm.day.slice(0, 3)} · in ${duration(nextAlarm.next_fire_in_s)}`}
          />
        )}

        <WeatherCard index={i++} weather={weather} />

        {playing && (
          <GlanceCard
            index={i++}
            tone="plain"
            onClick={() => navigate('music')}
            label="Playing"
            value={playing.title}
            detail={playing.artist}
            compact
            art={playing.art_id ? artUrl(playing.art_id) : null}
          />
        )}
      </section>

      <section className="home__apps" aria-label="Apps">
        {appTiles({ timers, alarms }).map((tile, n) => (
          <AppTile key={tile.route} tile={tile} index={n} />
        ))}
      </section>
    </main>
  )
}

/* ---------------------------------------------------------------------------
   Glance cards
   --------------------------------------------------------------------------- */

interface GlanceProps {
  index: number
  label: string
  value: string
  detail: string
  tone: 'accent' | 'info' | 'plain'
  onClick: () => void
  /** 0..1 — draws a thin fill across the bottom of the card. */
  progress?: number
  /** Adds the pulsing halo. For a timer at zero or about to be. */
  urgent?: boolean
  /** Smaller value type, for text that is a title rather than a number. */
  compact?: boolean
  art?: string | null
}

function GlanceCard({
  index,
  label,
  value,
  detail,
  tone,
  onClick,
  progress,
  urgent,
  compact,
  art,
}: GlanceProps) {
  return (
    <button
      type="button"
      className={`glance themed glance--${tone}${urgent ? ' is-urgent' : ''}`}
      style={{ '--i': index } as React.CSSProperties}
      onClick={onClick}
    >
      {urgent && <span className="glance__halo" aria-hidden />}

      {art && (
        /* Decorative: the title and artist below carry the information. */
        <img className="glance__art" src={art} alt="" aria-hidden />
      )}

      <span className="glance__label">{label}</span>
      <span className={`glance__value${compact ? ' is-compact' : ' num'}`}>
        {value}
      </span>
      <span className="glance__detail">{detail}</span>

      {progress !== undefined && (
        <span
          className="glance__progress"
          style={{ '--p': Math.min(1, Math.max(0, progress)) } as React.CSSProperties}
          aria-hidden
        />
      )}
    </button>
  )
}

function WeatherCard({
  index,
  weather,
}: {
  index: number
  weather: ReturnType<typeof useWeather>
}) {
  // No location in .env, or Open-Meteo unreachable. Said plainly rather than
  // hidden: a weather card that silently vanishes looks like a bug, and
  // "set WEATHER_LAT" is the actual fix.
  if (!weather || weather.status !== 'ok') {
    return (
      <div
        className="glance glance--plain is-quiet themed"
        style={{ '--i': index } as React.CSSProperties}
      >
        <span className="glance__label">Weather</span>
        <span className="glance__value is-compact">
          {weather?.status === 'unconfigured' ? 'No location set' : '--'}
        </span>
        <span className="glance__detail">
          {weather?.status === 'unconfigured'
            ? 'WEATHER_LAT / WEATHER_LON'
            : 'waiting for a reading'}
        </span>
      </div>
    )
  }

  const deg = weather.units === 'fahrenheit' ? 'F' : 'C'

  return (
    <div
      className="glance glance--plain themed"
      style={{ '--i': index } as React.CSSProperties}
    >
      <span className="glance__label">
        {weather.place || 'Weather'}
      </span>
      <span className="glance__value num">
        {weather.temp}°<span className="glance__unit">{deg}</span>
      </span>
      <span className="glance__detail">
        {weather.description}
        {weather.feels_like !== weather.temp && ` · feels ${weather.feels_like}°`}
      </span>
      <span className="glance__glyph" aria-hidden>
        <WeatherGlyph
          icon={weatherIcon(weather.code)}
          isDay={weather.is_day ?? true}
        />
      </span>
    </div>
  )
}

/* ---------------------------------------------------------------------------
   App grid
   --------------------------------------------------------------------------- */

interface Tile {
  route: Route
  name: string
  /** One line of live state, so the launcher is not just a list of nouns. */
  status: string
  icon: React.ReactNode
  /** Lights the tile's accent. Reserved for "something is happening here". */
  live?: boolean
}

const ICON = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

/* ONLY apps that are NOT in the sidebar (USER DECISION 2026-10-16). Music,
   Systems and Settings are rail destinations; repeating them here made the
   launcher a second copy of the navigation rather than a place where the
   things without a rail entry live. */
function appTiles({
  timers,
  alarms,
}: {
  timers: TimerEntry[]
  alarms: AlarmEntry[]
}): Tile[] {
  const enabled = alarms.filter((a) => a.enabled)

  // Counted by state, not just by length: "1 running" over a timer that is
  // actually paused is the launcher telling you something untrue about the
  // one thing you opened it to check.
  const counting = timers.filter((t) => !t.paused && !t.ringing).length
  const held = timers.filter((t) => t.paused).length

  return [
    {
      route: 'timers',
      name: 'Timers',
      status:
        timers.length === 0
          ? 'none running'
          : [counting > 0 && `${counting} running`, held > 0 && `${held} paused`]
              .filter(Boolean)
              .join(' · ') || 'ringing',
      live: counting > 0,
      icon: (
        <svg {...ICON} aria-hidden>
          <circle cx="12" cy="13.5" r="8" />
          <path d="M12 9.5v4l2.5 2M9 2h6M12 2v3" />
        </svg>
      ),
    },
    {
      route: 'alarms',
      name: 'Alarms',
      status:
        enabled.length === 0
          ? 'all off'
          : `${enabled.length} of 7 on`,
      live: enabled.length > 0,
      icon: (
        <svg {...ICON} aria-hidden>
          <path d="M6 9a6 6 0 1 1 12 0c0 4.5 1.5 6 1.5 6h-15S6 13.5 6 9Z" />
          <path d="M10 19a2.2 2.2 0 0 0 4 0" />
        </svg>
      ),
    },
    {
      route: 'wake',
      name: 'Home',
      // Deliberately NOT a live reading. This tile would otherwise have to
      // poll the backend's TCP probe from the launcher, and a probe that
      // runs whenever the panel is idle on the home screen is a knock on
      // that machine's port every few seconds, forever. The app itself
      // polls; the tile just opens it.
      status: 'wake the PC',
      icon: (
        <svg {...ICON} aria-hidden>
          <path d="M3.5 5.5h17v11h-17z" />
          <path d="M9 20.5h6M12 16.5v4" />
          <path d="M12 8.5v3.2" />
        </svg>
      ),
    },
  ]
}

function AppTile({ tile, index }: { tile: Tile; index: number }) {
  return (
    <button
      type="button"
      className={`apptile themed${tile.live ? ' is-live' : ''}`}
      style={{ '--i': index } as React.CSSProperties}
      onClick={() => navigate(tile.route)}
    >
      <span className="apptile__icon">{tile.icon}</span>
      <span className="apptile__name">{tile.name}</span>
      <span className="apptile__status">{tile.status}</span>
    </button>
  )
}
