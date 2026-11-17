// Inventory (retail_management.api.stock): stock on hand, movements, transfers, counts.
import { api } from './api'

const API = 'retail_management.api.stock'

export interface StockRow {
  item_code: string
  item_name: string
  item_group: string
  uom: string
  shop: string
  shop_name: string
  qty: number
  rate: number
  value: number
  reorder_level: number
  low: boolean
  out: boolean
}

export interface StockList {
  currency: string | null
  totals: { products: number; units: number; value: number; low: number; out: number }
  rows: StockRow[]
}

export type MovementKind = 'sale' | 'return' | 'receipt' | 'purchase' | 'transfer' | 'count' | 'other'

export interface Movement {
  posted: string
  item_code: string
  item_name: string
  shop_name: string
  kind: MovementKind
  qty: number
  balance: number
  voucher_type: string
  voucher_no: string
  /** a stock entry or count that an owner or manager may cancel */
  reversible: boolean
  by: string
}

export interface Reversal {
  voucher_type: string
  voucher_no: string
  posted: string
  cancelled: boolean
  lines: { item_code: string; item_name: string; shop_name: string; qty: number }[]
  by: string
}

export interface Transfer {
  name: string
  posted: string
  from_shop: string
  to_shop: string
  lines: { item_code: string; item_name: string; qty: number }[]
  qty: number
  reference: string
  by: string
}

export interface Count {
  name: string | null
  posted?: string
  shop_name?: string | null
  lines: { item_code: string; item_name: string; counted: number; before: number; difference: number; value_difference: number }[]
  value_difference: number
  reference?: string
  by?: string
  unchanged?: number
}

export interface QtyLine {
  item_code: string
  item_name: string
  barcode: string
  /** stock in the (source) shop when the line was added */
  in_stock: number
  qty: number | ''
}

export const stockApi = {
  stock: (shop: string, query: string, only: string) => api.get<StockList>(`${API}.get_stock`, { shop, query, only }),
  movements: (shop: string, kind: string, start: number, itemCode = '') =>
    api.get<{ rows: Movement[]; more: boolean }>(`${API}.get_movements`, {
      shop,
      kind,
      start: String(start),
      limit: '50',
      ...(itemCode ? { item_code: itemCode } : {}),
    }),
  transfer: (fromShop: string, toShop: string, lines: QtyLine[], reference: string, requestId: string) =>
    api.post<Transfer>(`${API}.transfer_stock`, {
      from_shop: fromShop,
      to_shop: toShop,
      reference,
      request_id: requestId,
      lines: lines.map((l) => ({ item_code: l.item_code, qty: Number(l.qty) })),
    }),
  transfers: (shop: string) => api.get<Transfer[]>(`${API}.get_transfers`, { shop, limit: '8' }),
  count: (shop: string, lines: QtyLine[], reference: string, requestId: string) =>
    api.post<Count>(`${API}.submit_count`, {
      shop,
      reference,
      request_id: requestId,
      lines: lines.map((l) => ({ item_code: l.item_code, qty: Number(l.qty) })),
    }),
  correct: (shop: string, itemCode: string, qty: number, reason: string, requestId: string) =>
    api.post<Count>(`${API}.correct_stock`, { shop, item_code: itemCode, qty, reason, request_id: requestId }),
  reversal: (voucherType: string, voucherNo: string) =>
    api.get<Reversal>(`${API}.get_reversal`, { voucher_type: voucherType, voucher_no: voucherNo }),
  reverse: (voucherType: string, voucherNo: string, reason: string) =>
    api.post<Reversal>(`${API}.reverse_movement`, { voucher_type: voucherType, voucher_no: voucherNo, reason }),
  counts: (shop: string) => api.get<Count[]>(`${API}.get_counts`, { shop, limit: '8' }),
}
