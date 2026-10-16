/**
 * A scrolling wheel picker — the hour/minute control.
 *
 * WHY THIS AND NOT ± BUTTONS
 *   The alarm time used to be two pairs of ± buttons, which is ten taps to
 *   move an alarm from 7:00 to 8:20. There is no keyboard on this panel and
 *   no on-screen one wanted, and Chromium's native <input type="time"> opens
 *   a picker that assumes one. A flick wheel is the control a phone alarm
 *   uses, for exactly this reason.
 *
 * HOW IT WORKS
 *   A scroll container with CSS scroll-snap. The browser does the physics,
 *   the snapping and the momentum; this component only reads which item ended
 *   up in the middle. That is why there is no drag maths here and no
 *   requestAnimationFrame loop: on a Pi, native scrolling is the one smooth
 *   thing available for free.
 *
 * THE FEEDBACK LOOP, AND HOW IT IS AVOIDED
 *   Reporting a value causes the parent to save it, which re-renders this
 *   with a new `value`, which would scroll the wheel mid-flick and fight the
 *   finger. So: a programmatic scroll is only ever performed when the wheel
 *   is NOT being touched, and `settling` suppresses the reporting that a
 *   programmatic scroll would otherwise trigger.
 *
 * ITEM HEIGHT LIVES IN CSS
 *   Read back from the custom property rather than duplicated as a constant
 *   here, so the two cannot drift when the compact layout shrinks the wheel.
 */
import { useCallback, useEffect, useRef } from 'react'
import './Drum.css'

export interface DrumItem {
  value: number
  label: string
}

export function Drum({
  items,
  value,
  onChange,
  ariaLabel,
}: {
  items: DrumItem[]
  value: number
  onChange: (value: number) => void
  ariaLabel: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const touching = useRef(false)
  const settling = useRef(false)
  const timer = useRef(0)

  const itemHeight = (el: HTMLElement) =>
    parseFloat(getComputedStyle(el).getPropertyValue('--drum-item')) || 48

  const scrollToValue = useCallback(
    (next: number, smooth: boolean) => {
      const el = ref.current
      if (!el) return
      const index = items.findIndex((i) => i.value === next)
      if (index < 0) return

      settling.current = true
      el.scrollTo({ top: index * itemHeight(el), behavior: smooth ? 'smooth' : 'auto' })

      // Long enough for a smooth scroll to finish. If this were shorter the
      // tail of our own animation would be read back as a user scroll.
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => {
        settling.current = false
      }, smooth ? 420 : 60)
    },
    [items],
  )

  // Follow the value from outside — a voice command, another browser, or the
  // day being switched — but never while a finger is on the wheel.
  useEffect(() => {
    if (touching.current) return
    scrollToValue(value, false)
  }, [value, scrollToValue])

  const onScroll = () => {
    const el = ref.current
    if (!el || settling.current) return

    window.clearTimeout(timer.current)
    // Debounced to the end of the flick: reporting every frame would save
    // every value the wheel passed through, which is a PUT per row of a
    // momentum scroll.
    timer.current = window.setTimeout(() => {
      const index = Math.round(el.scrollTop / itemHeight(el))
      const picked = items[Math.max(0, Math.min(items.length - 1, index))]
      if (picked && picked.value !== value) onChange(picked.value)
    }, 140)
  }

  return (
    <div className="drum" role="group" aria-label={ariaLabel}>
      <div
        ref={ref}
        className="drum__scroll"
        onScroll={onScroll}
        onPointerDown={() => {
          touching.current = true
        }}
        // Both, because a flick ends with the finger lifted but the scroll
        // still running: `pointerup` releases the lock, the debounce above is
        // what waits for the motion to stop.
        onPointerUp={() => {
          touching.current = false
        }}
        onPointerCancel={() => {
          touching.current = false
        }}
      >
        {items.map((item) => (
          <div
            key={item.value}
            className={`drum__item num${item.value === value ? ' is-current' : ''}`}
            aria-current={item.value === value ? 'true' : undefined}
          >
            {item.label}
          </div>
        ))}
      </div>

      {/* The lens over the middle row, and the fades top and bottom. Siblings
          rather than box-shadows on the scroller, so nothing repaints while
          the list moves. */}
      <div className="drum__lens" aria-hidden />
      <div className="drum__fade drum__fade--top" aria-hidden />
      <div className="drum__fade drum__fade--bottom" aria-hidden />
    </div>
  )
}
