// Team accounts (retail_management.api.users), for the owner.
import { api } from './api'

const API = 'retail_management.api.users'

export type Tier = 'owner' | 'partner' | 'manager' | 'cashier'
export const TIERS: Tier[] = ['owner', 'partner', 'manager', 'cashier']
/** Roles that work in chosen shops only (the others see every shop). */
export const SHOP_TIERS: Tier[] = ['manager', 'cashier']

export interface Account {
  name: string
  email: string
  first_name: string
  last_name: string
  full_name: string
  username: string
  enabled: number
  tier: Tier | null
  shops: string[]
  last_login: string | null
  me: boolean
}

export interface AccountForm {
  name?: string
  email: string
  first_name: string
  last_name: string
  username: string
  tier: Tier
  shops: string[]
  enabled: number
  /** empty = keep the current password */
  password: string
}

export interface Team {
  users: Account[]
  shops: { name: string; shop_name: string }[]
  username_login: number
}

export const usersApi = {
  list: () => api.get<Team>(`${API}.get_users`),
  save: (user: AccountForm) => api.post<Account>(`${API}.save_user`, { user }),
}

/** A strong random password that is easy to read out and type. */
export function generatePassword(): string {
  const letters = 'abcdefghjkmnpqrstuvwxyz'
  const digits = '23456789'
  const random = (n: number) => {
    const values = new Uint32Array(1)
    crypto.getRandomValues(values)
    return values[0] % n
  }
  const word = () => {
    let out = ''
    for (let i = 0; i < 4; i++) out += letters[random(letters.length)]
    return out[0].toUpperCase() + out.slice(1)
  }
  let number = ''
  for (let i = 0; i < 4; i++) number += digits[random(digits.length)]
  return `${word()}-${word()}-${word()}-${number}`
}
