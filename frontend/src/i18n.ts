import { createI18n } from 'vue-i18n'

import ar from './locales/ar.json'
import en from './locales/en.json'
import fr from './locales/fr.json'

export const LOCALES = ['en', 'fr', 'ar'] as const
export type Locale = (typeof LOCALES)[number]

const STORAGE_KEY = 'retail.locale'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, fr, ar },
})

export function toLocale(value: string | null | undefined): Locale | null {
  const short = value?.slice(0, 2).toLowerCase()
  return LOCALES.find((locale) => locale === short) ?? null
}

/** Switch language and text direction for the whole page. */
export function applyLocale(locale: Locale) {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // Storage can be unavailable (private mode); the choice then lasts for this page only.
  }
}

function storedLocale(): Locale | null {
  try {
    return toLocale(localStorage.getItem(STORAGE_KEY))
  } catch {
    return null
  }
}

/** Best guess before the site's settings have loaded. */
export function initialLocale(): Locale {
  return storedLocale() ?? toLocale(navigator.language) ?? 'en'
}

/**
 * Choose among the languages this site has enabled: an explicit preference
 * first, then this browser's last choice, the browser language, the site default.
 */
export function pickLocale(enabled: Locale[], fallback: Locale, preferred?: Locale | null): Locale {
  const candidates = [preferred, storedLocale(), toLocale(navigator.language), fallback]
  return candidates.find((locale) => locale && enabled.includes(locale)) ?? enabled[0] ?? 'en'
}
