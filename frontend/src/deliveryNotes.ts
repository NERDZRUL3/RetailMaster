// Supplier delivery notes read from a PDF or photo (retail_management.api.delivery_notes).
import { api } from './api'
import type { SupplierInvoice } from './purchasing'

const API = 'retail_management.api.delivery_notes'

export interface DraftLine {
  item_code: string
  item_name: string
  qty: number | ''
  /** unit cost read from the note, if any */
  rate: number | '' | null
  /** last known cost, shown when the note has none */
  suggested_rate?: number | null
  /** the text the line was read from */
  raw?: string
  /** current stock per shop (shop name → qty) */
  stock: Record<string, number>
}

export interface UnmatchedLine {
  raw: string
  qty: number
  rate: number | null
}

export interface NoteDraft {
  file: string
  file_name: string
  /** "text": read from the PDF itself; "ocr": read from a scan, check it */
  method: 'text' | 'ocr'
  text: string
  supplier: string | null
  supplier_name: string | null
  reference: string
  date: string | null
  order: string | null
  shop: string | null
  orders: { name: string; shop: string; shop_name: string; date: string; overlap: number }[]
  lines: DraftLine[]
  unmatched: UnmatchedLine[]
}

export interface NoteToReceive {
  supplier: string
  shop: string
  order: string
  reference: string
  file: string
  lines: DraftLine[]
}

export const deliveryNotesApi = {
  read: (file: File) => api.upload<NoteDraft>(`${API}.read_delivery_note`, file),
  receive: (note: NoteToReceive, requestId: string) =>
    api.post<SupplierInvoice>(`${API}.receive_delivery_note`, {
      note: {
        ...note,
        lines: note.lines
          .filter((l) => Number(l.qty) > 0)
          .map((l) => ({
            item_code: l.item_code,
            qty: Number(l.qty),
            ...(l.rate !== '' && l.rate !== null ? { rate: Number(l.rate) } : {}),
          })),
      },
      request_id: requestId,
    }),
  downloadUrl: (receipt: string) => `/api/method/${API}.download?receipt=${encodeURIComponent(receipt)}`,
}
