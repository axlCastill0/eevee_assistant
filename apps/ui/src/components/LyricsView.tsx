/**
 * The lyrics overlay on the music view.
 *
 * It sits INSIDE .np, over the stage and under nothing, so the drifting cover
 * colours behind it are the same ones the track already painted -- the view
 * changes what is on the background, never the background.
 *
 * FOLLOWING THE SONG
 *   The active line is found from the same interpolated `progressMs` the
 *   progress bar uses, and is kept centred with scrollIntoView. That is a
 *   scroll rather than a transform, which this project otherwise avoids
 *   animating -- but it happens once per sung line, on a small composited
 *   scroller, and it is the only approach that stays correct when a long line
 *   wraps to three.
 *
 *   An unsynced set has no active line. It scrolls by finger instead and says
 *   so, because a page that looks like it should follow and does not reads as
 *   broken.
 */
import { useEffect, useMemo, useRef } from 'react'
import type { Lyrics } from '../lib/api'
import { activeLine } from '../lib/useLyrics'
import { Icon } from './Term'
import './LyricsView.css'

export function LyricsView({
  lyrics,
  title,
  artist,
  progressMs,
  onClose,
}: {
  lyrics: Lyrics
  title: string
  artist: string
  progressMs: number
  onClose: () => void
}) {
  const lines = lyrics.lines ?? []
  const synced = !!lyrics.synced

  const current = useMemo(
    () => (synced ? activeLine(lines, progressMs) : -1),
    [synced, lines, progressMs],
  )

  const activeRef = useRef<HTMLParagraphElement | null>(null)

  useEffect(() => {
    if (!synced) return
    activeRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [current, synced])

  return (
    <div className="lyrics" role="dialog" aria-label={`Lyrics for ${title}`}>
      <header className="lyrics__head">
        <div className="lyrics__meta">
          <span className="lyrics__title">{title}</span>
          <span className="lyrics__artist">{artist}</span>
        </div>

        {!synced && (
          /* Said once, at the top, rather than next to every line. */
          <span className="lyrics__unsynced">not timed · scroll</span>
        )}

        <button
          type="button"
          className="lyrics__close"
          aria-label="Close lyrics"
          onClick={onClose}
        >
          <Icon name="close" />
        </button>
      </header>

      <div className="lyrics__scroll">
        {/* Half a screen of padding top and bottom, so the first and last
            lines can still reach the middle. */}
        <div className="lyrics__pad" aria-hidden />

        {lines.map((line, i) => (
          <p
            key={`${i}-${line.t ?? 0}`}
            ref={i === current ? activeRef : undefined}
            /* The entrance stagger, capped: a 60-line song must not still be
               arriving a second after the view opened. Set here rather than
               in CSS so the cap is arithmetic rather than a nested min(). */
            style={{ animationDelay: `${Math.min(i * 18, 420)}ms` }}
            className={`lyrics__line${
              i === current ? ' is-current' : ''
            }${synced && i < current ? ' is-past' : ''}${
              line.text ? '' : ' is-gap'
            }`}
          >
            {/* A timed gap keeps its space in the scroll so an instrumental
                break reads as one, instead of jumping the next verse up. */}
            {line.text || '·'}
          </p>
        ))}

        <div className="lyrics__pad" aria-hidden />
      </div>
    </div>
  )
}
