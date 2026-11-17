// Overview dashboard data (retail_management.api.dashboard) and formatting.
import { api } from './api'

const API = 'retail_management.api.dashboard'

export type Period = '7d' | '30d' | '12m'
export const PERIODS: Period[] = ['7d', '30d', '12m']

export type KpiKey = 'revenue' | 'sales' | 'average' | 'returns'

export interface Kpi {
  value: number
  previous: number
  /** Percentage change against the previous period; null when there was nothing before. */
  change: number | null
}

export interface Bucket {
  /** YYYY-MM-DD, or YYYY-MM for monthly periods */
  key: string
  total: number
  by_shop: Record<string, number>
}

export interface RecentSale {
  name: string
  date: string
  customer: string
  shop_name: string
  items: number
  total: number
  is_return: boolean
  status: string
}

export interface Overview {
  period: Period
  start: string
  end: string
  monthly: boolean
  currency: string | null
  shops: { name: string; shop_name: string }[]
  kpis: Partial<Record<KpiKey, Kpi>>
  series: Bucket[]
  recent: RecentSale[]
  low_stock: number
}

export const dashboardApi = {
  overview: (period: Period, shop: string) => api.get<Overview>(`${API}.get_overview`, { period, shop }),
  counts: () => api.get<{ low_stock: number }>(`${API}.get_counts`),
}

/** 12.5k, 1.2M: for chart axes. */
export function formatCompact(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function parseKey(key: string): Date {
  const [year, month, day] = key.split('-').map(Number)
  return new Date(year, month - 1, day || 1)
}

/** Short label under a bar: weekday (7 days), day of month (30 days), month (12 months). */
export function bucketLabel(key: string, period: Period, locale: string): string {
  const date = parseKey(key)
  if (period === '12m') return new Intl.DateTimeFormat(locale, { month: 'short' }).format(date)
  if (period === '7d') return new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(date)
  return String(date.getDate())
}

/** Full label for tooltips and screen readers. */
export function bucketTitle(key: string, monthly: boolean, locale: string): string {
  const date = parseKey(key)
  return new Intl.DateTimeFormat(
    locale,
    monthly ? { month: 'long', year: 'numeric' } : { weekday: 'long', day: 'numeric', month: 'long' },
  ).format(date)
}

export function formatDate(key: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(parseKey(key))
}
