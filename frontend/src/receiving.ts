// Receiving deliveries into a shop (retail_management.api.receiving).
import { api } from './api'

const API = 'retail_management.api.receiving'

export interface Receipt {
  name: string
  /** local date and time, YYYY-MM-DDTHH:MM:SS */
  posted: string
  shop_name: string
  lines: number
  qty: number
  value: number
  reference: string
  by: string
}

export interface ReceiveLine {
  item_code: string
  item_name: string
  stock_uom: string
  barcode: string
  /** stock in this shop before the delivery */
  in_stock: number
  qty: number
  /** unit cost; empty keeps the current cost */
  rate: number | ''
}

export const receivingApi = {
  receive: (shop: string, lines: ReceiveLine[], reference: string, requestId: string) =>
    api.post<Receipt>(`${API}.receive_stock`, {
      shop,
      reference,
      request_id: requestId,
      lines: lines.map((line) => ({ item_code: line.item_code, qty: line.qty, rate: line.rate })),
    }),
  receipts: (shop: string) => api.get<Receipt[]>(`${API}.get_receipts`, { shop, limit: '8' }),
}

// The delivery being scanned survives a trip to "create product" and a page
// reload, per shop, for this browser tab only.
const key = (shop: string) => `retail.receive.${shop}`

export function loadDraft(shop: string): { lines: ReceiveLine[]; reference: string } {
  try {
    const raw = sessionStorage.getItem(key(shop))
    if (raw) return JSON.parse(raw)
  } catch {
    // storage blocked or corrupt: start empty
  }
  return { lines: [], reference: '' }
}

export function saveDraft(shop: string, draft: { lines: ReceiveLine[]; reference: string }) {
  try {
    if (draft.lines.length || draft.reference) sessionStorage.setItem(key(shop), JSON.stringify(draft))
    else sessionStorage.removeItem(key(shop))
  } catch {
    // not saved; the page still works
  }
}

export function newRequestId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
