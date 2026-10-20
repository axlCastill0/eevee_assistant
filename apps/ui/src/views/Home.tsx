/**
 * Home — the launcher, as a terminal's opening report.
 *
 * STRUCTURE
 *   A typed heading, a row of framed glance cards, then the app grid. The two
 *   sections are separated by labelled rules rather than by whitespace, so the
 *   page reads as output rather than as a layout.
 *
 * THE GLANCE STRIP IS CONDITIONAL
 *   A card appears only when it has something to say: timers while any exist,
 *   the next alarm only while one is enabled, now playing only while
 *   something is actually playing. Weather is the exception and is always
 *   there -- it is the one thing on this screen worth reading when nothing at
 *   all is happening, and a home screen that empties to nothing reads as
 *   broken.
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
import type { GlyphName } from '../fonts/glyphs'
import { Icon, Meter, Rule } from '../components/Term'
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
      {/* A static dot matrix. The one piece of atmosphere on the page, and it
          is a background-image rather than an element: nothing moves. */}
      <div className="home__matrix" aria-hidden />

      <header className="home__head">
        <span className="home__prompt prompt" aria-hidden>
          ❯
        </span>
        <h1 className="home__title">Dashboard</h1>
        <span className="caret" aria-hidden />
      </header>

      <Rule label="glance" icon="pulse" />

      <section className="home__glance" aria-label="At a glance">
        {soonest && (
          <GlanceCard
            index={i++}
            icon="timer"
            tone="accent"
            onClick={() => navigate('timers')}
            label={timers.length > 1 ? 'timers' : 'timer'}
            meta={timers.length > 1 ? String(timers.length) : undefined}
            value={soonest.ringing ? 'done' : countdown(soonest.remaining_s)}
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
            icon="bell"
            tone="info"
            onClick={() => navigate('alarms')}
            label="next alarm"
            value={nextAlarm.label}
            detail={`${nextAlarm.day.slice(0, 3)} · in ${duration(nextAlarm.next_fire_in_s)}`}
          />
        )}

        <WeatherCard index={i++} weather={weather} />

        {playing && (
          <GlanceCard
            index={i++}
            icon="music"
            tone="plain"
            onClick={() => navigate('music')}
            label="playing"
            value={playing.title}
            detail={playing.artist}
            compact
            art={playing.art_id ? artUrl(playing.art_id) : null}
          />
        )}
      </section>

      <Rule label="apps" icon="tasks" />

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
  icon: GlyphName
  tone: 'accent' | 'info' | 'plain'
  onClick: () => void
  /** Right-hand side of the card's title bar. */
  meta?: string
  /** 0..1 — drawn as a block meter under the value. */
  progress?: number
  /** Reddens the frame. For a timer at zero or about to be. */
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
  icon,
  tone,
  onClick,
  meta,
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
      <span className="glance__bar">
        <Icon name={icon} className="glance__icon" />
        <span className="glance__label">{label}</span>
        <span className="glance__fill" aria-hidden>
          ──────────────────────────────────────
        </span>
        {meta && <span className="glance__meta num">{meta}</span>}
      </span>

      <span className="glance__main">
        {art && (
          /* Decorative: the title and artist carry the information. */
          <img className="glance__art" src={art} alt="" aria-hidden />
        )}
        <span className="glance__text">
          <span className={`glance__value${compact ? ' is-compact' : ' num'}`}>
            {value}
          </span>
          <span className="glance__detail">{detail}</span>
        </span>
      </span>

      {progress !== undefined && (
        <span className="glance__meter">
          <Meter value={progress} cells={14} tone={urgent ? 'down' : 'accent'} />
        </span>
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
        <span className="glance__bar">
          <Icon name="cloud" className="glance__icon" />
          <span className="glance__label">weather</span>
          <span className="glance__fill" aria-hidden>
            ──────────────────────────────────────
          </span>
        </span>
        <span className="glance__main">
          <span className="glance__text">
            <span className="glance__value is-compact">
              {weather?.status === 'unconfigured' ? 'no location' : '--'}
            </span>
            <span className="glance__detail mono">
              {weather?.status === 'unconfigured'
                ? 'WEATHER_LAT / WEATHER_LON'
                : 'waiting for a reading'}
            </span>
          </span>
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
      <span className="glance__bar">
        <span className="glance__icon glance__icon--weather">
          <WeatherGlyph
            icon={weatherIcon(weather.code)}
            isDay={weather.is_day ?? true}
          />
        </span>
        <span className="glance__label">{weather.place || 'weather'}</span>
        <span className="glance__fill" aria-hidden>
          ──────────────────────────────────────
        </span>
      </span>

      <span className="glance__main">
        <span className="glance__text">
          <span className="glance__value num">
            {weather.temp}°<span className="glance__unit">{deg}</span>
          </span>
          <span className="glance__detail">
            {weather.description}
            {weather.feels_like !== weather.temp && ` · feels ${weather.feels_like}°`}
          </span>
        </span>
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
  icon: GlyphName
  /** Lights the tile's accent. Reserved for "something is happening here". */
  live?: boolean
}

/* ONLY apps that are NOT in the rail (USER DECISION 2026-10-16). Music,
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
      icon: 'timer',
      status:
        timers.length === 0
          ? 'none running'
          : [counting > 0 && `${counting} running`, held > 0 && `${held} paused`]
              .filter(Boolean)
              .join(' · ') || 'ringing',
      live: counting > 0,
    },
    {
      route: 'alarms',
      name: 'Alarms',
      icon: 'bell',
      status: enabled.length === 0 ? 'all off' : `${enabled.length} of 7 on`,
      live: enabled.length > 0,
    },
    {
      route: 'training',
      name: 'Fingers',
      icon: 'pulse',
      // Not a live reading: the session lives in its own view and there is no
      // backend state to ask about it.
      status: '3 × 6 · 9:00',
    },
    {
      route: 'wake',
      name: 'Home',
      icon: 'pc',
      // Deliberately NOT a live reading. This tile would otherwise have to
      // poll the backend's TCP probe from the launcher, and a probe that runs
      // whenever the panel is idle on the home screen is a knock on that
      // machine's port every few seconds, forever.
      status: 'wake the PC',
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
      <span className="apptile__run" aria-hidden>
        ./{tile.route}
      </span>
      <Icon name={tile.icon} className="apptile__icon" />
      <span className="apptile__name">{tile.name}</span>
      <span className="apptile__status">{tile.status}</span>
    </button>
  )
}
