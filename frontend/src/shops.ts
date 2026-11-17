// Shop setup for the owner (retail_management.api.shops).
import { api } from './api'

const API = 'retail_management.api.shops'

export interface ShopRow {
  name: string
  shop_name: string
  enabled: number
  company: string
  warehouse: string | null
}

export const shopsApi = {
  setup: () => api.get<{ shops: ShopRow[]; companies: string[] }>(`${API}.get_shop_setup`),
  create: (shopName: string, company?: string) =>
    api.post<ShopRow>(`${API}.create_shop`, { shop_name: shopName, ...(company ? { company } : {}) }),
  setEnabled: (shop: string, enabled: boolean) =>
    api.post<ShopRow>(`${API}.set_shop_enabled`, { shop, enabled: enabled ? 1 : 0 }),
}
