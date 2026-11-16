// Light or dark interface. The choice is per device (a shop till and a
// phone can differ), so it lives in the browser, not on the user profile.
// index.html applies it before the first paint; this module keeps it in sync.
import { reactive } from 'vue'

export type ThemeChoice = 'system' | 'light' | 'dark'
export const THEME_CHOICES: ThemeChoice[] = ['system', 'light', 'dark']

const STORAGE_KEY = 'retail.theme'
const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')

function stored(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (value === 'light' || value === 'dark') return value
  } catch {
    // Storage blocked (private window, previews): follow the device.
  }
  return 'system'
}

export const theme = reactive({ choice: stored() })

function apply() {
  const dark = theme.choice === 'dark' || (theme.choice === 'system' && darkQuery.matches)
  document.documentElement.classList.toggle('dark', dark)
}

export function setTheme(choice: ThemeChoice) {
  theme.choice = choice
  try {
    if (choice === 'system') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, choice)
  } catch {
    // Not saved; still applied for this visit.
  }
  apply()
}

export function initTheme() {
  apply()
  darkQuery.addEventListener('change', apply)
}
