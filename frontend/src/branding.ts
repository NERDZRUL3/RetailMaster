// Per-customer branding. It comes from the server (Retail Settings) with every
// session load, so nothing about one business is built into the interface.
import { reactive } from 'vue'

import type { Locale } from './i18n'

export interface Branding {
  app_name: string
  logo: string | null
  /** Exactly as the customer chose it: accents, rings, borders. */
  brand_color: string
  /** Same hue, darkened only if needed so white text on it is readable. */
  brand_color_strong: string
  default_language: Locale
  languages: Locale[]
}

export const branding = reactive<Branding>({
  app_name: '',
  logo: null,
  brand_color: '',
  brand_color_strong: '',
  default_language: 'en',
  languages: ['en', 'fr', 'ar'],
})

const HEX = /^#[0-9a-f]{6}$/i

export function applyBranding(next: Branding) {
  Object.assign(branding, next)
  document.title = next.app_name
  // styles.css derives every brand shade from these two variables.
  const root = document.documentElement.style
  if (HEX.test(next.brand_color)) root.setProperty('--brand', next.brand_color)
  if (HEX.test(next.brand_color_strong)) root.setProperty('--brand-strong', next.brand_color_strong)
}

// Same rule as the server (retail_settings.readable_shade), used for the live
// preview on the Settings page. The server's value is what gets applied.
function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5)
}

export function contrastWithWhite(hex: string): number {
  return 1.05 / (luminance(hex) + 0.05)
}

export function readableShade(hex: string): string {
  if (!HEX.test(hex)) return hex
  if (contrastWithWhite(hex) >= 4.5) return hex.toLowerCase()
  const rgb = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  for (let step = 1; step <= 100; step++) {
    const factor = 1 - step / 100
    const shade = '#' + rgb.map((c) => Math.round(c * factor).toString(16).padStart(2, '0')).join('')
    if (contrastWithWhite(shade) >= 4.5) return shade
  }
  return '#000000'
}
