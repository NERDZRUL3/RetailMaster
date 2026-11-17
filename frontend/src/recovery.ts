// Getting back into an account (retail_management.api.recovery): an email
// link through Frappe, or one of the owner's printed recovery codes.
import { api } from './api'

const API = 'retail_management.api.recovery'

export interface RecoveryStatus {
  remaining: number
  total: number
  created: string | null
}

export const recoveryApi = {
  options: () => api.get<{ email: boolean }>(`${API}.options`),
  status: () => api.get<RecoveryStatus>(`${API}.get_status`),
  generate: () => api.post<{ codes: string[]; remaining: number }>(`${API}.generate_codes`),
  resetWithCode: (account: string, code: string, newPassword: string) =>
    api.post<{ ok: boolean; remaining: number }>(`${API}.reset_with_code`, {
      account,
      code,
      new_password: newPassword,
    }),
  /** Frappe sends the link; it answers the same whether or not the account exists. */
  emailLink: (user: string) => api.post<void>('frappe.core.doctype.user.user.reset_password', { user }),
}
