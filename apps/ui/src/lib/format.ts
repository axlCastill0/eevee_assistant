/** Formatting helpers. All output is ASCII-safe for the kiosk's font stack. */

/** Compact duration: 4s, 2m, 1h 20m, 3d. */
export function duration(seconds: number | null): string {
  if (seconds === null) return '--'
  const s = Math.max(0, Math.round(seconds))

  if (s < 60) return `${s}s`
  if (s < 3600) {
    const m = Math.floor(s / 60)
    const rem = s % 60
    return rem && m < 10 ? `${m}m ${rem}s` : `${m}m`
  }
  if (s < 86400) {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    return m ? `${h}h ${m}m` : `${h}h`
  }
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  return h ? `${d}d ${h}h` : `${d}d`
}

/**
 * 12-hour time.
 *
 * The hour is NOT zero-padded -- "9:05" rather than "09:05" -- which is the
 * convention everywhere 12-hour time is used, and it keeps the glyph count
 * down on the big clock. Minutes and seconds stay padded.
 *
 * Matches the backend's spoken format (intents.get_time uses %-I:%M %p), so
 * the panel and the voice assistant report the same wall time the same way.
 */
export function clockTime(d: Date): {
  hm: string
  seconds: string
  meridiem: string
} {
  const h24 = d.getHours()
  // Midnight and noon are 12, not 0.
  const h12 = h24 % 12 === 0 ? 12 : h24 % 12
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return {
    hm: `${h12}:${mm}`,
    seconds: ss,
    meridiem: h24 < 12 ? 'AM' : 'PM',
  }
}

const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export function longDate(d: Date): string {
  return `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`
}

/** Title-cases a service id for display: "voice" -> "Voice". */
export function serviceLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1)
}

/** "3s ago" / "just now" for the last-updated readout. */
export function agoLabel(ms: number | null): string {
  if (ms === null) return 'never'
  const s = Math.round((Date.now() - ms) / 1000)
  if (s <= 1) return 'just now'
  return `${s}s ago`
}
