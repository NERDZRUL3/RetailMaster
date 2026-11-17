// Point of sale (retail_management.api.pos).
import { api } from './api'
import type { SessionInfo } from './till'

const API = 'retail_management.api.pos'

export interface Till {
  shop: string
  shop_name: string
  currency: string
  payments: { mode: string; cash: boolean; default: number }[]
  /** the till's open session, if any */
  session: SessionInfo | null
  /** owner or manager: may close someone else's session, sees expected amounts */
  can_manage: boolean
  /** cash counted at the last close, to suggest as the opening float */
  last_cash: number | null
}

export interface PosProduct {
  item_code: string
  item_name: string
  item_group: string
  uom: string
  image: string | null
  barcode: string
  price: number
  stock: number
}

export interface CartLine {
  item_code: string
  item_name: string
  price: number
  stock: number
  qty: number
}

export interface Sale {
  name: string
  posted: string
  shop: string | null
  shop_name: string | null
  company: string
  currency: string
  cashier: string
  customer: string
  lines: { item_code: string; item_name: string; qty: number; rate: number; amount: number }[]
  total: number
  taxes: number
  discount: number
  payments: { mode: string; amount: number }[]
  paid: number
  change: number
}

export interface SaleRow {
  name: string
  time: string
  total: number
  is_return: number
}

export const posApi = {
  till: (shop: string) => api.get<Till>(`${API}.get_till`, { shop }),
  find: (shop: string, query = '') => api.get<PosProduct[]>(`${API}.find_products`, { shop, query }),
  sell: (shop: string, lines: CartLine[], payments: { mode: string; amount: number }[], requestId: string) =>
    api.post<Sale>(`${API}.submit_sale`, {
      shop,
      request_id: requestId,
      lines: lines.map((line) => ({ item_code: line.item_code, qty: line.qty })),
      payments,
    }),
  sale: (name: string) => api.get<Sale>(`${API}.get_sale`, { name }),
  sales: (shop: string) => api.get<SaleRow[]>(`${API}.get_sales`, { shop, limit: '8' }),
}

// The cart survives a page reload, per shop, for this browser tab only.
const key = (shop: string) => `retail.pos.${shop}`

export function loadCart(shop: string): CartLine[] {
  try {
    const raw = sessionStorage.getItem(key(shop))
    if (raw) return JSON.parse(raw)
  } catch {
    // storage blocked or corrupt: start empty
  }
  return []
}

export function saveCart(shop: string, lines: CartLine[]) {
  try {
    if (lines.length) sessionStorage.setItem(key(shop), JSON.stringify(lines))
    else sessionStorage.removeItem(key(shop))
  } catch {
    // not saved; the till still works
  }
}

/** ERPNext's standard payment methods in the user's language; others as named. */
export function methodLabel(mode: string, t: (key: string) => string): string {
  if (mode === 'Cash') return t('pos.cash')
  if (mode === 'Credit Card') return t('pos.card')
  return mode
}

/** Banknote-friendly amounts a customer is likely to hand over. */
export function quickCash(total: number): number[] {
  const out = new Set<number>([Math.round(total * 100) / 100])
  for (const step of [10, 20, 50, 100, 200]) {
    const up = Math.ceil(total / step) * step
    if (up > total) out.add(up)
  }
  return [...out].sort((a, b) => a - b).slice(0, 5)
}
