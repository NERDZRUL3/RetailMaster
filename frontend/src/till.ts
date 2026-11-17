// Till sessions (retail_management.api.till): open, cash in/out, X and Z reports, close.
import { api } from './api'

const API = 'retail_management.api.till'

export interface SessionInfo {
  name: string
  user: string
  user_name: string
  mine: boolean
  /** local date and time, YYYY-MM-DDTHH:MM:SS */
  opened: string
  /** opened on an earlier day: must be closed before selling */
  outdated: boolean
}

export interface ReportRow {
  mode: string
  cash: boolean
  opening: number
  sales: number
  cash_in: number
  cash_out: number
  /** null while open for staff who do not manage the shop (blind count) */
  expected: number | null
  counted: number | null
  difference: number | null
}

export interface SessionReport {
  name: string
  closing_entry: string | null
  shop: string | null
  shop_name: string
  user: string
  user_name: string
  opened: string
  closed: string | null
  currency: string
  sales_count: number
  sales_total: number
  returns_count: number
  returns_total: number
  total: number
  taxes: number
  items: number
  rows: ReportRow[]
  movements: { type: 'In' | 'Out'; amount: number; reason: string; time: string; by: string }[]
  note: string | null
}

export interface SessionRow {
  name: string
  user_name: string
  opened: string
  closed: string | null
  total: number | null
  difference: number | null
  open: boolean
}

export type Counts = Record<string, number>

export const tillApi = {
  open: (shop: string, cash: number) => api.post<SessionInfo>(`${API}.open_session`, { shop, cash }),
  move: (shop: string, movementType: 'In' | 'Out', amount: number, reason: string) =>
    api.post<SessionReport>(`${API}.add_cash_movement`, { shop, movement_type: movementType, amount, reason }),
  current: (shop: string) => api.get<SessionReport>(`${API}.get_session`, { shop }),
  preview: (shop: string, counts: Counts) => api.post<SessionReport>(`${API}.preview_close`, { shop, counts }),
  close: (shop: string, counts: Counts, note: string) =>
    api.post<SessionReport>(`${API}.close_session`, { shop, counts, note }),
  report: (name: string) => api.get<SessionReport>(`${API}.get_report`, { name }),
  list: (shop: string) => api.get<SessionRow[]>(`${API}.list_sessions`, { shop, limit: '30' }),
}

/** "17/11/2026 09:12" in the user's language, from a local ISO timestamp. */
export function formatWhen(iso: string | null, locale: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })
}
