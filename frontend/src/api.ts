import { getAccessToken, logout } from './session'

// Формы ответов из docs/openapi.json и сообщений из docs/websocket.md.
export type Role = 'owner' | 'editor' | 'viewer'
export type DocumentMeta = {
  id: string; title: string; owner_id: string; role: Role
  generation: number; state_revision: number; created_at: string; updated_at: string
}
export type User = { id: string; email: string; display_name: string }
export type TokenResponse = { access_token: string; token_type: string; expires_in: number }
export type Member = {
  user_id: string; email: string; display_name: string; role: 'editor' | 'viewer'
  notification: 'not_configured' | 'queued' | 'queue_failed'
}
export type Version = {
  id: string; document_id: string; source_revision: number; created_at: string
  created_by: string | null; kind: 'manual' | 'scheduled' | 'export'
}
export type ExportStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type ExportJob = { id: string; status: ExportStatus; error_code: string | null; created_at: string; finished_at: string | null }
export type ExportAccepted = { task_id: string }
export type ControlMessage = { status: 'saved' | 'unsaved' | 'error' | 'role_changed'; role?: Role; revision?: number; generation?: number }

// WebSocket идёт на тот же origin, что и страница: ws локально, wss за HTTPS.
export function wsUrl(path: string): string {
  return `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${path}`
}

// JSON и файлы используют одинаковую проверку сессии и ошибок сервера.
export async function apiResponse(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken()
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  })
  if (response.status === 401) logout()
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
