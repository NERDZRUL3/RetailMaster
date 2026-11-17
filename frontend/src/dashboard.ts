// Dashboard data (retail_management.api.dashboard) and formatting helpers.
import { api } from './api'

const API = 'retail_management.api.dashboard'

export type Range = 'all' | 'weekly' | 'monthly'
export const RANGES: Range[] = ['all', 'weekly', 'monthly']

export interface Share {
  /** null for the "Other" slice */
  name: string | null
  value: number
  percent: number
}

export interface Dashboard {
  currency: string | null
  shops: { name: string; shop_name: string }[]
  today: string
  low_stock: number
  // The rest is missing when the user has no shop.
  sales?: {
    value: number
    previous: number
    change: number | null
    series: { date: string; value: number }[]
  }
  revenue?: {
    value: number
    change: number | null
    last_month: number
    week: { this: number; last: number }[]
  }
  customers?: {
    current: number
    current_change: number | null
    new: number
    new_change: number | null
    by_shop: { shop_name: string; sales: number; percent: number; change: number | null }[]
  }
  categories?: Record<Range, Share[]>
  hours?: Record<Range, { label: string; percent: number }[]>
  orders?: { date: string; income: number; profit: number }[]
  products?: {
    item_code: string
    name: string
    stock: number
    list_price: number
    price: number
    discount: number
    sold: number
  }[]
  recent?: {
    name: string
    customer: string
    amount: number
    is_return: boolean
    shop_name: string
    /** local date and time, YYYY-MM-DDTHH:MM:SS */
    posted: string
  }[]
}

export const dashboardApi = {
  get: (shop = '') => api.get<Dashboard>(`${API}.get_dashboard`, { shop }),
  counts: () => api.get<{ low_stock: number; currency: string | null }>(`${API}.get_counts`),
}

/** 12.5k, 1.2M: for chart axes. */
export function formatCompact(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

/** A YYYY-MM-DD date in the user's language. */
export function formatDay(iso: string, locale: string, options: Intl.DateTimeFormatOptions): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat(locale, options).format(new Date(year, month - 1, day))
}

/** "2 hours ago", "yesterday", from a local YYYY-MM-DDTHH:MM:SS timestamp. */
export function timeAgo(posted: string, locale: string): string {
  const seconds = (new Date(posted).getTime() - Date.now()) / 1000
  const format = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  const abs = Math.abs(seconds)
  if (abs < 3600) return format.format(Math.round(seconds / 60), 'minute')
  if (abs < 86400) return format.format(Math.round(seconds / 3600), 'hour')
  return format.format(Math.round(seconds / 86400), 'day')
}
