/**
 * Weather icons, inline.
 *
 * Same reasoning as the sidebar's icons: stroke-only SVG on a 24 grid, so
 * they inherit currentColor and the project still has no icon package. The
 * sun and the moon are different glyphs because a clear night drawn as a sun
 * is the kind of wrongness you notice from across a room.
 */
import type { WeatherIcon } from '../lib/useWeather'

const S = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function WeatherGlyph({ icon, isDay }: { icon: WeatherIcon; isDay: boolean }) {
  switch (icon) {
    case 'clear':
      return isDay ? (
        <svg {...S} aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" />
        </svg>
      ) : (
        <svg {...S} aria-hidden>
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />
        </svg>
      )
    case 'partly':
      return (
        <svg {...S} aria-hidden>
          <circle cx="8.5" cy="8" r="3.2" />
          <path d="M8.5 2.2v1.6M2.7 8h1.6M4.4 3.9l1.1 1.1" />
          <path d="M8 19h9a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.3 1.3A3 3 0 0 0 8 19Z" />
        </svg>
      )
    case 'cloud':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 18h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 18Z" />
        </svg>
      )
    case 'fog':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 14h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 14Z" />
          <path d="M4 18h16M7 21.5h11" />
        </svg>
      )
    case 'drizzle':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 14h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 14Z" />
          <path d="M9 17.5v1.5M13 17.5v1.5M17 17.5v1.5" />
        </svg>
      )
    case 'rain':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 13.5h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 13.5Z" />
          <path d="M8.5 16.5 7 21M13 16.5 11.5 21M17.5 16.5 16 21" />
        </svg>
      )
    case 'snow':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 13.5h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 13.5Z" />
          <path d="M9 18h.01M12.5 20.5h.01M16 18h.01M12.5 16.8h.01" />
        </svg>
      )
    case 'storm':
      return (
        <svg {...S} aria-hidden>
          <path d="M7.5 13.5h9.5a4 4 0 0 0 .3-8 5.6 5.6 0 0 0-10.5 1.4A3.4 3.4 0 0 0 7.5 13.5Z" />
          <path d="M13 16h-2.5l-1.5 3h3l-1 3 4-4.5h-2.5Z" />
        </svg>
      )
  }
}
