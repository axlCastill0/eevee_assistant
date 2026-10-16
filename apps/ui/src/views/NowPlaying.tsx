/**
 * Spotify now playing.
 *
 * LAYOUT
 *   One row, centred in both axes: cover on the left, everything else on the
 *   right, both boxes the same size. The size is one custom property
 *   (--np-size) derived from the viewport, so the two halves cannot drift
 *   apart and the whole thing scales from a 1024x600 panel to a 1080p one.
 *
 * CONTROLS
 *   previous / play-pause / next. No scrub: the bar is a readout (USER
 *   DECISION 2026-10-16). That also removes the only control on this page
 *   that would need a drag gesture, which is the one interaction a resistive
 *   touch panel is bad at.
 *
 * BACKGROUND
 *   The two dominant cover colours, as a gradient. Two stacked layers
 *   crossfaded on track change, because a gradient cannot be transitioned
 *   directly and opacity is compositor-only -- the rule the rest of this UI
 *   follows for the same reason.
 */
import { useEffect, useRef, useState } from 'react'
import { artUrl, fetchSpotifyLogin, type NowPlaying as Snapshot } from '../lib/api'
import { coverColors, NEUTRAL, type CoverColors } from '../lib/coverColors'
import { useSpotify } from '../lib/useSpotify'
import './NowPlaying.css'

/** mm:ss, and h:mm:ss only when a track is actually that long (podcasts). */
function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const s = total % 60
  const m = Math.floor(total / 60) % 60
  const h = Math.floor(total / 3600)
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

const NOTICES: Record<string, string> = {
  no_device: 'Nothing is playing on your account — start a track on another device first',
  premium_required: 'Spotify Premium is required to control playback',
  unauthorized: 'Spotify needs reconnecting',
  unconfigured: 'Spotify is not set up on this backend',
  rate_limited: 'Spotify is rate-limiting us; try again in a moment',
  unreachable: 'Could not reach Spotify',
}

export function NowPlaying({ active }: { active: boolean }) {
  const { data, loading, error, progressMs, notice, send } = useSpotify(active)

  const item = data?.status === 'ok' ? data.item : undefined
  const art = item?.art_id ? artUrl(item.art_id) : null

  // Two background layers, swapped on every cover change. `front` says which
  // one is currently visible, so the other is the one to paint into.
  const [layers, setLayers] = useState<[CoverColors, CoverColors]>([NEUTRAL, NEUTRAL])
  const [front, setFront] = useState(0)
  const lastArt = useRef<string | null>(null)

  useEffect(() => {
    if (art === lastArt.current) return
    lastArt.current = art

    if (!art) {
      setLayers((prev) => (front === 0 ? [prev[0], NEUTRAL] : [NEUTRAL, prev[1]]))
      setFront((f) => 1 - f)
      return
    }

    let cancelled = false
    void coverColors(art).then((colors) => {
      // A fast skip can resolve two extractions out of order; only the latest
      // cover may paint.
      if (cancelled || lastArt.current !== art) return
      setLayers((prev) => (front === 0 ? [prev[0], colors] : [colors, prev[1]]))
      setFront((f) => 1 - f)
    })
    return () => {
      cancelled = true
    }
  }, [art, front])

  const duration = item?.duration_ms ?? 0
  // Clamped: a stale snapshot plus local advance can overshoot by a tick at
  // the end of a track, and a bar wider than its track looks broken.
  const fraction = duration > 0 ? Math.min(1, Math.max(0, progressMs / duration)) : 0

  return (
    <div className="np" data-fg={layers[front].foreground}>
      {/* Both layers always rendered; only opacity changes. */}
      {[0, 1].map((i) => (
        <div
          key={i}
          className={`np__bg${front === i ? ' is-front' : ''}`}
          style={
            {
              '--c-a': layers[i].a,
              '--c-b': layers[i].b,
            } as React.CSSProperties
          }
          aria-hidden
        />
      ))}

      {item ? (
        <div className="np__stage">
          {/* The cover drifts while a track plays. Three transforms on three
              nested elements with co-prime-ish periods (7s / 11s / 13s), so
              they only realign every few minutes and the loop never reads as
              a loop. Pausing does not REMOVE the animations -- it sets
              `animation-play-state: paused`, so the art stops where it is
              instead of snapping back to square. */}
          <div className={`np__cover-float${data?.is_playing ? ' is-playing' : ''}`}>
            <div className="np__cover">
              {art ? (
                /* key on the id so a track change remounts the <img> and the
                   fade-in replays instead of the new cover popping in. */
                <img key={item.art_id} className="np__cover-img" src={art}
                     alt={`${item.album} cover`} draggable={false} />
              ) : (
                <div className="np__cover-empty" aria-hidden>♪</div>
              )}
            </div>
          </div>

          <div className="np__panel">
            <div className="np__meta">
              <div className="np__eyebrow">
                {data?.is_playing ? 'Now playing' : 'Paused'}
                {data?.device?.name && (
                  <>
                    <span className="np__dot" aria-hidden />
                    <span className="np__device">{data.device.name}</span>
                  </>
                )}
              </div>

              {/* Title scales with its own length: a 60-character song name
                  must not wrap into the controls. */}
              <h1 className="np__title" data-len={item.title.length > 34 ? 'long' : 'short'}>
                {item.title}
              </h1>
              <p className="np__artist">{item.artist}</p>
              {item.album && item.album !== item.title && (
                <p className="np__album">{item.album}</p>
              )}
            </div>

            <div className="np__bar">
              {/* scaleX, not width: the only properties this UI animates are
                  transform and opacity. */}
              <div className="np__bar-track">
                <div
                  className="np__bar-fill"
                  style={{ transform: `scaleX(${fraction})` }}
                />
              </div>
              <div className="np__times">
                <span className="num">{clock(progressMs)}</span>
                <span className="num np__times-total">{clock(duration)}</span>
              </div>
            </div>

            <div className="np__controls">
              <button
                type="button"
                className="np__btn"
                aria-label="Previous track"
                onClick={() => send('previous')}
              >
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path d="M19 5.5v13L9.5 12 19 5.5Z" fill="currentColor" />
                  <rect x="5" y="5" width="2.6" height="14" rx="1.3" fill="currentColor" />
                </svg>
              </button>

              <button
                type="button"
                className="np__btn np__btn--primary"
                aria-label={data?.is_playing ? 'Pause' : 'Play'}
                onClick={() => send('toggle')}
              >
                {data?.is_playing ? (
                  <svg viewBox="0 0 24 24" aria-hidden>
                    <rect x="6" y="4.5" width="4" height="15" rx="1.6" fill="currentColor" />
                    <rect x="14" y="4.5" width="4" height="15" rx="1.6" fill="currentColor" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" aria-hidden>
                    <path d="M7.5 4.6 19.5 12 7.5 19.4V4.6Z" fill="currentColor" />
                  </svg>
                )}
              </button>

              <button
                type="button"
                className="np__btn"
                aria-label="Next track"
                onClick={() => send('next')}
              >
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path d="M5 5.5v13L14.5 12 5 5.5Z" fill="currentColor" />
                  <rect x="16.4" y="5" width="2.6" height="14" rx="1.3" fill="currentColor" />
                </svg>
              </button>
            </div>

            {/* Spotify's design guidelines require attribution wherever their
                content is shown. It also doubles as the "where is this from"
                answer on a panel with several sources. */}
            <div className="np__source">Spotify</div>
          </div>
        </div>
      ) : (
        <Empty snapshot={data} loading={loading} error={error} />
      )}

      {notice && <div className="np__notice">{NOTICES[notice] ?? notice}</div>}

      {data?.degraded && item && (
        <div className="np__stale">
          {data.degraded === 'rate_limited' ? 'rate limited' : 'reconnecting'}
        </div>
      )}
    </div>
  )
}

/** Everything that is not a playing track: starting up, nothing playing, not
 *  connected yet, backend down. Each one says what to do next rather than
 *  showing an empty frame. */
function Empty({
  snapshot,
  loading,
  error,
}: {
  snapshot: Snapshot | null
  loading: boolean
  error: string | null
}) {
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const needsAuth = snapshot?.status === 'unauthorized'

  // Minted on demand: the state inside it is single-use and expires, so there
  // is no point fetching one until the screen that needs it is on display.
  useEffect(() => {
    if (!needsAuth) return
    void fetchSpotifyLogin()
      .then((r) => setAuthUrl(r.authorize_url))
      .catch(() => setAuthUrl(null))
  }, [needsAuth])

  let title = 'Nothing playing'
  let body = 'Start something on any Spotify device and it shows up here.'

  if (loading) {
    title = 'Loading'
    body = ''
  } else if (error) {
    title = 'Backend unreachable'
    body = error
  } else if (snapshot?.status === 'unconfigured') {
    title = 'Spotify not set up'
    body = 'SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are not set on the backend. See docs/SPOTIFY.md.'
  } else if (needsAuth) {
    title = 'Connect Spotify'
    body = 'One consent screen, once. The Pi stays connected afterwards.'
  } else if (snapshot?.status === 'unreachable') {
    title = 'Spotify unreachable'
    body = 'The backend could not reach Spotify. It will keep trying.'
  } else if (snapshot?.status === 'rate_limited') {
    title = 'Rate limited'
    body = 'Spotify asked us to slow down. Back shortly.'
  }

  return (
    <div className="np__empty">
      <div className="np__empty-title">{title}</div>
      {body && <p className="np__empty-body">{body}</p>}
      {needsAuth && authUrl && (
        /* A real link, not a fetch: the consent screen has to render in a
           browser, and this kiosk IS a browser on the right machine, so the
           redirect to 127.0.0.1 resolves correctly. */
        <a className="np__empty-cta" href={authUrl} rel="noreferrer">
          Open Spotify login
        </a>
      )}
    </div>
  )
}
