/**
 * Weather, as one glyph from the Nerd Font's weather set.
 *
 * The day and night variants are different glyphs because a clear night drawn
 * as a sun is the kind of wrongness you notice from across a room.
 */
import type { GlyphName } from '../fonts/glyphs'
import type { WeatherIcon } from '../lib/useWeather'
import { Icon } from './Term'

const DAY: Record<WeatherIcon, GlyphName> = {
  clear: 'clear_day',
  partly: 'partly_day',
  cloud: 'cloud',
  fog: 'fog_day',
  drizzle: 'drizzle',
  rain: 'rain_day',
  snow: 'snow_day',
  storm: 'storm_day',
}

const NIGHT: Record<WeatherIcon, GlyphName> = {
  ...DAY,
  clear: 'clear_night',
  partly: 'partly_night',
  fog: 'fog_night',
  rain: 'rain_night',
  snow: 'snow_night',
  storm: 'storm_night',
}

export function WeatherGlyph({ icon, isDay }: { icon: WeatherIcon; isDay: boolean }) {
  return <Icon name={(isDay ? DAY : NIGHT)[icon]} />
}
