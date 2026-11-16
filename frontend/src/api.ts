// Thin client for Frappe's /api/method endpoints. Uses the Frappe session
// cookie; state-changing calls carry the CSRF token from the session API.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

let csrfToken = ''

export function setCsrfToken(token: string) {
  csrfToken = token
}

/** Frappe puts user-facing messages in _server_messages as nested JSON. */
function errorMessage(data: Record<string, unknown> | null, fallback: string): string {
  try {
    const messages = JSON.parse(String(data?._server_messages ?? '[]')) as string[]
    const first = messages.length ? (JSON.parse(messages[0]) as { message?: string }).message : undefined
    if (first) return first.replace(/<[^>]*>/g, '')
  } catch {
    // fall through
  }
  return String(data?.exception ?? data?.message ?? fallback)
}

async function send<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...init })
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.statusText))
  return data?.message as T
}

function writeHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { Accept: 'application/json', ...(csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {}), ...extra }
}

export const api = {
  get<T>(path: string, params?: Record<string, string>): Promise<T> {
    const query = params ? `?${new URLSearchParams(params)}` : ''
    return send<T>(`/api/method/${path}${query}`, { method: 'GET', headers: { Accept: 'application/json' } })
  },
  post<T>(path: string, params?: Record<string, unknown>): Promise<T> {
    return send<T>(`/api/method/${path}`, {
      method: 'POST',
      headers: writeHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(params ?? {}),
    })
  },
  upload<T>(path: string, file: File): Promise<T> {
    const form = new FormData()
    form.append('file', file)
    return send<T>(`/api/method/${path}`, { method: 'POST', headers: writeHeaders(), body: form })
  },
}
