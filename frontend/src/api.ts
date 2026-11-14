import { getAccessToken, setAccessToken } from './session'

export type Document = {
  id: string; title: string; owner_id: string; role: 'owner' | 'editor' | 'viewer'
  generation: number; state_revision: number; updated_at: string
}
export type User = { id: string; email: string; display_name: string }

// JSON и файлы используют одинаковую проверку сессии и ошибок сервера.
export async function apiResponse(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken()
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  })
  if (response.status === 401) {
    setAccessToken(null)
    window.dispatchEvent(new Event('cowrite:logout'))
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: string | { message?: string } }
    const message = typeof data.detail === 'string' ? data.detail : data.detail?.message
    throw new Error(message || (response.status === 403 ? 'Нет доступа' : `Ошибка ${response.status}`))
  }
  return response
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiResponse(path, init)
  return (response.status === 204 ? undefined : await response.json()) as T
}
