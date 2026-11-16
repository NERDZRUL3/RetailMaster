// Types and helpers shared by the product pages.
import { api } from './api'

export interface ShopStock {
  shop: string
  shop_name: string
  qty: number
  reorder_level: number
  reorder_qty: number
  low: boolean
}

export interface Product {
  item_code: string
  item_name: string
  item_group: string
  stock_uom: string
  brand: string | null
  disabled: number
  image: string | null
  description?: string | null
  barcodes: string[]
  price: number | null
  currency: string | null
  stock: ShopStock[]
  total_qty: number
  low: boolean
}

export interface FormOptions {
  item_groups: string[]
  uoms: string[]
  brands: string[]
  default_uom: string
  default_item_group: string | null
  price_list: string | null
  currency: string | null
  shops: { name: string; shop_name: string }[]
  can_create: boolean
  can_write: boolean
}

const API = 'retail_management.api.inventory'

export const inventoryApi = {
  search: (query: string, shop: string, lowOnly: boolean) =>
    api.get<Product[]>(`${API}.search_items`, { query, shop, low_only: lowOnly ? '1' : '0' }),
  get: (code: string) => api.get<Product>(`${API}.get_item`, { item_code: code }),
  options: () => api.get<FormOptions>(`${API}.get_form_options`),
  save: (item: Record<string, unknown>) => api.post<Product>(`${API}.save_item`, { item }),
}

export function formatQty(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(value)
}

export function formatMoney(value: number | null, currency: string | null, locale: string): string {
  if (value === null || value === undefined) return '—'
  if (!currency) return new Intl.NumberFormat(locale, { minimumFractionDigits: 2 }).format(value)
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(value)
  } catch {
    return `${value.toFixed(2)} ${currency}`
  }
}
