/**
 * The two dominant colours of a cover, for the page background.
 *
 * METHOD
 *   Draw the image into a 32x32 offscreen canvas (the browser's own
 *   downscale is free and does the averaging for us), bucket the pixels into
 *   a coarse 5-bit-per-channel histogram, then pick the heaviest bucket and
 *   the heaviest bucket that is far enough from it in hue/lightness to read
 *   as a second colour.
 *
 *   32x32 is 1024 samples. That is plenty to find dominant colour and it
 *   keeps the whole pass under a millisecond on a Pi 5 -- this runs on every
 *   track change, so it has to be cheap enough to be invisible.
 *
 * WHY NOT A LIBRARY
 *   node-vibrant and friends are ~40 KB for a better answer to a harder
 *   question (palette extraction with saturation weighting). This needs two
 *   colours for a gradient behind large text, and the quality bar is "does it
 *   look like the cover", not "is it the perceptually optimal palette".
 *
 * WHEN THERE IS ONLY ONE COLOUR
 *   A mono cover (a lot of them are) yields one bucket and nothing far
 *   enough away. Rather than show a flat wash, the second colour is derived:
 *   same hue, rotated slightly and pushed the other way in lightness, so the
 *   gradient still has direction. That is the "closest shade or generate one"
 *   case.
 *
 * SAME-ORIGIN
 *   The image comes from /api/spotify/art/<id>, proxied by our backend, so
 *   getImageData() is readable. A direct i.scdn.co URL would taint the canvas
 *   unless their CORS headers cooperate, and that is not a thing to depend on.
 */

export interface CoverColors {
  /** CSS rgb() strings, darkened enough to sit behind white text. */
  a: string
  b: string
  /** Which foreground reads on top of them. */
  foreground: 'light' | 'dark'
}

/** The fallback is the app's own surface colours, so a missing cover looks
 *  deliberate rather than broken. */
export const NEUTRAL: CoverColors = {
  a: 'rgb(26, 28, 34)',
  b: 'rgb(12, 13, 16)',
  foreground: 'light',
}

/** The "nothing playing" palette (USER DECISION 2026-10-25): red into black,
 *  to match the disc's artwork.
 *
 *  It is a CoverColors like any other, which is the point -- the idle screen
 *  reuses the view's existing background machinery (two drifting blobs and a
 *  90s sheen, crossfaded on change) rather than owning a second one. When a
 *  track starts, the real cover's colours crossfade in over the top exactly
 *  as one cover does into another. */
export const IDLE: CoverColors = {
  a: 'rgb(150, 20, 26)',
  b: 'rgb(11, 8, 9)',
  foreground: 'light',
}

type Rgb = [number, number, number]

const SIZE = 32
/** 5 bits per channel: 32 levels, 32768 buckets. Fine enough that two shades
 *  of the same colour do not merge, coarse enough that noise does not split a
 *  dominant colour across buckets. */
const SHIFT = 3

function toHsl([r, g, b]: Rgb): [number, number, number] {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const l = (max + min) / 2
  const d = max - min
  if (d === 0) return [0, 0, l]

  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  if (max === rn) h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6
  else if (max === gn) h = ((bn - rn) / d + 2) / 6
  else h = ((rn - gn) / d + 4) / 6
  return [h * 360, s, l]
}

function fromHsl(h: number, s: number, l: number): Rgb {
  const hn = ((h % 360) + 360) % 360 / 360
  if (s === 0) {
    const v = Math.round(l * 255)
    return [v, v, v]
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  const channel = (t: number) => {
    let tn = t
    if (tn < 0) tn += 1
    if (tn > 1) tn -= 1
    if (tn < 1 / 6) return p + (q - p) * 6 * tn
    if (tn < 1 / 2) return q
    if (tn < 2 / 3) return p + (q - p) * (2 / 3 - tn) * 6
    return p
  }
  return [
    Math.round(channel(hn + 1 / 3) * 255),
    Math.round(channel(hn) * 255),
    Math.round(channel(hn - 1 / 3) * 255),
  ]
}

/** Distance in a cylinder that treats hue as meaningless when saturation is
 *  low -- otherwise two near-greys 180 degrees apart look "different" and the
 *  gradient ends up grey-to-grey. */
function distance(x: Rgb, y: Rgb): number {
  const [h1, s1, l1] = toHsl(x)
  const [h2, s2, l2] = toHsl(y)
  let dh = Math.abs(h1 - h2)
  if (dh > 180) dh = 360 - dh
  const hueWeight = Math.min(s1, s2)
  return (dh / 180) * hueWeight * 1.6 + Math.abs(l1 - l2) + Math.abs(s1 - s2) * 0.4
}

/** Push a colour into the band that works as a full-bleed background behind
 *  large type: keep its hue, clamp lightness away from both extremes, and
 *  keep a little saturation so it does not read as grey. */
function asBackground(rgb: Rgb, target: number): Rgb {
  const [h, s, l] = toHsl(rgb)
  const sat = Math.min(0.72, Math.max(s, 0.18))
  // Nudge towards the target lightness rather than snapping to it, so a cover
  // that is genuinely dark stays dark and a bright one stays bright-ish.
  const lightness = l * 0.35 + target * 0.65
  return fromHsl(h, sat, lightness)
}

function css([r, g, b]: Rgb): string {
  return `rgb(${r}, ${g}, ${b})`
}

/**
 * Extract the two colours. Resolves to NEUTRAL on any failure -- a tainted
 * canvas, a 404 cover, an image that never loads. The page always has a
 * background.
 */
export function coverColors(src: string): Promise<CoverColors> {
  return new Promise((resolve) => {
    const image = new Image()
    // Same-origin already, but this also keeps the canvas untainted if the
    // proxy is ever bypassed.
    image.crossOrigin = 'anonymous'
    image.decoding = 'async'

    image.onerror = () => resolve(NEUTRAL)
    image.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = SIZE
        canvas.height = SIZE
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) return resolve(NEUTRAL)

        ctx.drawImage(image, 0, 0, SIZE, SIZE)
        const { data } = ctx.getImageData(0, 0, SIZE, SIZE)

        const buckets = new Map<number, { count: number; sum: Rgb }>()
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 128) continue        // transparent pixels say nothing
          const r = data[i]
          const g = data[i + 1]
          const b = data[i + 2]
          const key =
            ((r >> SHIFT) << 10) | ((g >> SHIFT) << 5) | (b >> SHIFT)
          const entry = buckets.get(key)
          if (entry) {
            entry.count += 1
            entry.sum[0] += r
            entry.sum[1] += g
            entry.sum[2] += b
          } else {
            buckets.set(key, { count: 1, sum: [r, g, b] })
          }
        }

        if (buckets.size === 0) return resolve(NEUTRAL)

        const ranked = [...buckets.values()]
          .sort((x, y) => y.count - x.count)
          .map(({ count, sum }): { count: number; rgb: Rgb } => ({
            count,
            rgb: [
              Math.round(sum[0] / count),
              Math.round(sum[1] / count),
              Math.round(sum[2] / count),
            ],
          }))

        const primary = ranked[0].rgb

        // The second colour must be visibly different, and must still be one
        // of the cover's own colours -- so this walks the ranked list rather
        // than taking the most distant pixel, which on most covers is a
        // single bright speck.
        const MIN_DISTANCE = 0.22
        let secondary: Rgb | null = null
        for (const candidate of ranked.slice(1, 12)) {
          if (distance(primary, candidate.rgb) >= MIN_DISTANCE) {
            secondary = candidate.rgb
            break
          }
        }

        if (!secondary) {
          // Monochrome cover: derive the partner. A small hue rotation plus an
          // opposite lightness shift gives the gradient somewhere to go.
          const [h, s, l] = toHsl(primary)
          secondary = fromHsl(h + 18, s, l > 0.5 ? l - 0.22 : l + 0.22)
        }

        // Ordered darkest-last so the gradient always falls off towards the
        // bottom right, which is where the controls sit.
        const [lighter, darker] =
          toHsl(primary)[2] >= toHsl(secondary)[2]
            ? [primary, secondary]
            : [secondary, primary]

        resolve({
          a: css(asBackground(lighter, 0.34)),
          b: css(asBackground(darker, 0.14)),
          // The band chosen above is always dark enough for white text; this
          // stays explicit so a future lighter band only needs one change.
          foreground: 'light',
        })
      } catch {
        // getImageData throws on a tainted canvas. Not fatal.
        resolve(NEUTRAL)
      }
    }

    image.src = src
  })
}
