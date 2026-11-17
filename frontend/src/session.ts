import { reactive } from 'vue'

import { api, setCsrfToken } from './api'
import { applyBranding, type Branding } from './branding'
import { applyLocale, type Locale, pickLocale, toLocale } from './i18n'

export type Home = 'owner' | 'manager' | 'cashier'

export interface Shop {
  name: string
  shop_name: string
  retail_business: string
  company: string
}

export interface SessionContext {
  authenticated: true
  branding: Branding
  user: string
  full_name: string
  language: string | null
  home: Home | null
  shops: Shop[]
  can_edit_settings: boolean
  /** Owners and managers: may receive deliveries into their shops. */
  can_receive?: boolean
  /** Owners, managers and cashiers: may sell at the till. */
  can_sell?: boolean
  /** Owners and managers: may manage suppliers and purchase orders. */
  can_buy?: boolean
  /** Owners: may manage the team's accounts. */
  can_manage_users?: boolean
  csrf_token: string
}

type ContextResponse = SessionContext | { authenticated: false; branding: Branding }

export const session = reactive<{ loaded: boolean; context: SessionContext | null }>({
  loaded: false,
  context: null,
})

export function homePath(home: Home | null | undefined): string {
  if (home === 'owner') return '/owner'
  if (home === 'cashier') return session.context?.can_sell ? '/pos' : '/shop'
  if (home === 'manager') return '/shop'
  return '/no-access'
}

export async function loadSession(): Promise<SessionContext | null> {
  const response = await api.get<ContextResponse>('retail_management.api.session.get_context')
  applyBranding(response.branding)
  session.context = response.authenticated ? response : null
  session.loaded = true

  if (session.context) setCsrfToken(session.context.csrf_token)

  // The language saved on the user's profile wins, then this browser's last
  // choice, then the browser language, then the site default.
  const saved = toLocale(session.context?.language)
  applyLocale(pickLocale(response.branding.languages, response.branding.default_language, saved))

  return session.context
}

export async function login(email: string, password: string): Promise<SessionContext | null> {
  await api.post('login', { usr: email, pwd: password })
  return loadSession()
}

export async function logout() {
  await api.post('logout')
  session.context = null
  setCsrfToken('')
}

/** Change language now, and remember it on the user's profile when signed in. */
export async function chooseLocale(locale: Locale) {
  applyLocale(locale)
  if (session.context) {
    await api.post('retail_management.api.session.set_language', { language: locale })
    session.context.language = locale
  }
}
