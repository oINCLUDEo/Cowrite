import { useEffect, useState } from 'react'
import { WebsocketProvider } from 'y-websocket'
import * as Y from 'yjs'
import { wsUrl, type ControlMessage, type DocumentMeta } from './api'
import { OFFLINE, saveStatusLabels } from './labels'
import { getAccessToken, logout } from './session'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

// Y.Doc с провайдером и то, что о соединении показывает шапка. Вызывается до useEditor: ему нужна session.
export function useCollabSession(metadata: DocumentMeta) {
  const documentId = metadata.id
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [saved, setSaved] = useState('Синхронизация…')
  const [role, setRole] = useState(metadata.role)
  const [error, setError] = useState('')
  // Один Y.Doc и одно соединение на открытый редактор, не на каждый рендер.
  const [session] = useState(() => {
    const doc = new Y.Doc()
    const provider = new WebsocketProvider(
      wsUrl('/ws/documents'),
      documentId,
      doc,
      { connect: false, params: { token: getAccessToken() || '', generation: String(metadata.generation) } },
    )
    // Имя и цвет курсора не определяют права пользователя.
    const colors = ['#2563eb', '#c026d3', '#059669', '#d97706']
    return {
      document: doc,
      provider,
      user: {
        name: `Участник ${doc.clientID.toString(16).slice(-4)}`,
        color: colors[doc.clientID % colors.length],
      },
    }
  })
  return { session, status, setStatus, saved, setSaved, role, setRole, error, setError }
}

// Подключение, переподключение и коды закрытия. Вызывается после эффектов useEditor, как раньше в Editor.
export function useCollabConnection(collab: ReturnType<typeof useCollabSession>, metadata: DocumentMeta, reload: () => void) {
  const { session, setStatus, setSaved, setRole, setError } = collab
  const documentId = metadata.id
  useEffect(() => {
    // Подключаемся после монтирования; при уходе со страницы убираем соединение и Y.Doc.
    let control: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout>
    let active = true
    const openControl = () => {
      if (!active || !navigator.onLine || control?.readyState === WebSocket.OPEN || control?.readyState === WebSocket.CONNECTING) return
      control = new WebSocket(wsUrl(`/ws/documents/${documentId}/status?token=${encodeURIComponent(getAccessToken() || '')}&generation=${metadata.generation}`))
      control.onmessage = (event) => {
        const data = JSON.parse(String(event.data)) as ControlMessage
        if (data.role) setRole(data.role)
        if (data.status !== 'role_changed') setSaved(saveStatusLabels[data.status] || 'Синхронизация…')
      }
      control.onclose = () => { if (active) { setSaved(OFFLINE); reconnect = setTimeout(openControl, 2000) } }
    }
    const onStatus = ({ status: value }: { status: ConnectionStatus }) => {
      setStatus(value)
      if (value === 'connected') openControl()
      else setSaved(OFFLINE)
    }
    const onClose = (event: CloseEvent | null) => {
      if (event?.code === 4409) {
        session.provider.disconnect()
        window.alert('Восстановлена другая версия. Редактор будет перезагружен.')
        reload()
      } else if (event?.code === 4401) {
        logout()
      } else if (event?.code === 4403 || event?.code === 4404) {
        session.provider.disconnect()
        setRole('viewer')
        setError(event.code === 4404 ? 'Документ удалён' : 'Доступ закрыт')
      }
    }
    const offline = () => {
      session.provider.disconnect()
      control?.close()
      setStatus('disconnected')
      setSaved(OFFLINE)
    }
    const online = () => { session.provider.connect() }
    window.addEventListener('offline', offline)
    window.addEventListener('online', online)
    session.provider.on('status', onStatus)
    session.provider.on('connection-close', onClose)
    session.provider.connect()
    return () => {
      session.provider.off('status', onStatus)
      session.provider.off('connection-close', onClose)
      window.removeEventListener('offline', offline)
      window.removeEventListener('online', online)
      active = false
      clearTimeout(reconnect)
      control?.close()
      session.provider.destroy()
      session.document.destroy()
    }
  }, [session, documentId, metadata.generation, reload, setStatus, setSaved, setRole, setError])
}
