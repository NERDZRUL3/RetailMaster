// Product categories: groups and subgroups (retail_management.api.categories).
import { api } from './api'

const API = 'retail_management.api.categories'

export interface Subgroup {
  name: string
  items: number
}
export interface Group extends Subgroup {
  children: Subgroup[]
}
export interface CategoryTree {
  root: string
  groups: Group[]
  can_create: boolean
  can_write: boolean
  can_delete: boolean
}

export const categoriesApi = {
  get: () => api.get<CategoryTree>(`${API}.get_categories`),
  /** Create (no name) or rename/move (name). parent '' = a top-level group. */
  save: (label: string, name = '', parent = '') =>
    api.post<{ name: string }>(`${API}.save_category`, { label, name, parent }),
  remove: (name: string) => api.post<{ deleted: string }>(`${API}.delete_category`, { name }),
}

/** Group and subgroup of a product's category, from the tree. */
export function locate(tree: CategoryTree | null, category: string): { group: string; subgroup: string } {
  for (const group of tree?.groups ?? []) {
    if (group.name === category) return { group: group.name, subgroup: '' }
    if (group.children.some((child) => child.name === category)) return { group: group.name, subgroup: category }
  }
  return { group: category, subgroup: '' }
}
