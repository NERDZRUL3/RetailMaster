// Suppliers and purchase orders (retail_management.api.purchasing).
import { api } from './api'

const API = 'retail_management.api.purchasing'

export interface Supplier {
  name: string
  supplier_name: string
  phone: string
  email: string
  notes: string
  disabled: number
  open_orders?: number
}

export type OrderStatus = 'draft' | 'ordered' | 'partly_received' | 'received' | 'closed' | 'cancelled'

export interface OrderRow {
  name: string
  status: OrderStatus
  supplier_name: string
  shop_name: string
  date: string
  expected: string | null
  late: boolean
  total: number
  currency: string
  qty: number
  per_received: number
}

export interface OrderLine {
  row?: string
  item_code: string
  item_name: string
  uom?: string
  qty: number | ''
  received?: number
  remaining?: number
  rate: number | ''
  amount?: number
}

export interface Order {
  name: string
  status: OrderStatus
  supplier: string
  supplier_name: string
  shop: string | null
  shop_name: string
  company: string
  currency: string
  date: string
  expected: string | null
  notes: string
  total: number
  per_received: number
  lines: {
    row: string
    item_code: string
    item_name: string
    uom: string
    qty: number
    received: number
    remaining: number
    rate: number
    amount: number
  }[]
  receipts: { name: string; date: string; reference: string; by: string }[]
  by: string
}

export interface OrderDraft {
  name?: string
  supplier: string
  shop: string
  expected: string
  notes: string
  lines: OrderLine[]
}

/** A delivery from a supplier (Purchase Receipt) with its invoice, if entered. */
export interface SupplierInvoice {
  receipt: string
  invoice: string | null
  bill_no: string
  bill_date: string | null
  outstanding: number | null
  supplier: string
  supplier_name: string
  shop_name: string
  date: string
  total: number
  qty: number
  currency: string
  orders: string[]
  /** the supplier's invoice is entered for all of it */
  billed: boolean
  /** a delivery note file is attached */
  attachment: string | null
  by: string
}

/** A line of a supplier invoice: a row of the order (row set) or any product. */
export interface InvoiceLine {
  row?: string
  item_code: string
  item_name: string
  qty: number | ''
  rate: number | ''
  /** for order rows: quantity still expected */
  remaining?: number
}

export interface InvoiceDraft {
  supplier: string
  shop: string
  order: string
  bill_no: string
  bill_date: string
  lines: InvoiceLine[]
}

export const purchasingApi = {
  invoices: (shop: string) => api.get<SupplierInvoice[]>(`${API}.get_supplier_invoices`, { shop }),
  invoiceReceipt: (receipt: string, billNo: string, billDate: string, requestId: string) =>
    api.post<SupplierInvoice>(`${API}.invoice_receipt`, {
      receipt,
      bill_no: billNo,
      bill_date: billDate,
      request_id: requestId,
    }),
  enterInvoice: (draft: InvoiceDraft, requestId: string) =>
    api.post<SupplierInvoice>(`${API}.receive_invoice`, {
      invoice: {
        ...draft,
        lines: draft.lines
          .filter((l) => Number(l.qty) > 0)
          .map((l) =>
            l.row ? { row: l.row, qty: Number(l.qty) } : { item_code: l.item_code, qty: Number(l.qty), rate: Number(l.rate) || 0 },
          ),
      },
      request_id: requestId,
    }),
  suppliers: (query = '') => api.get<Supplier[]>(`${API}.get_suppliers`, { query }),
  saveSupplier: (supplier: Partial<Supplier>) => api.post<Supplier>(`${API}.save_supplier`, { supplier }),
  orders: (shop: string, status: string, query: string) => api.get<OrderRow[]>(`${API}.get_orders`, { shop, status, query }),
  order: (name: string) => api.get<Order>(`${API}.get_order`, { name }),
  save: (order: OrderDraft, submit: boolean, requestId: string) =>
    api.post<Order>(`${API}.save_order`, {
      order: {
        ...order,
        lines: order.lines.map((l) => ({ item_code: l.item_code, qty: Number(l.qty), rate: Number(l.rate) || 0 })),
      },
      submit: submit ? 1 : 0,
      request_id: requestId,
    }),
  submit: (name: string) => api.post<Order>(`${API}.submit_order`, { name }),
  remove: (name: string) => api.post<{ deleted: string }>(`${API}.delete_order`, { name }),
  cancel: (name: string) => api.post<Order>(`${API}.cancel_order`, { name }),
  close: (name: string) => api.post<Order>(`${API}.close_order`, { name }),
  receive: (name: string, lines: { row: string; qty: number }[], reference: string, requestId: string) =>
    api.post<Order>(`${API}.receive_order`, { name, lines, reference, request_id: requestId }),
  costs: (codes: string[], supplier: string) =>
    api.get<Record<string, number>>(`${API}.get_item_costs`, { item_codes: JSON.stringify(codes), supplier }),
}

export const STATUS_BADGE: Record<OrderStatus, string> = {
  draft: 'badge-neutral',
  ordered: 'badge-brand',
  partly_received: 'badge-warn',
  received: 'badge-ok',
  closed: 'badge-neutral',
  cancelled: 'badge-neutral',
}

/** YYYY-MM-DD a number of days from today, local time. */
export function inDays(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
