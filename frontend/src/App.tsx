import { useCallback, useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCaret from '@tiptap/extension-collaboration-caret'
import { WebsocketProvider } from 'y-websocket'
import * as Y from 'yjs'
import { OAuthCallback } from './OAuthCallback'
import { Auth } from './Auth'
import { Documents } from './Documents'
import { Export, History, Share } from './Panels'
import { api, type Document } from './api'
import { getAccessToken, setAccessToken } from './session'

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

function Editor({ metadata, reload, back }: { metadata: Document; reload: () => void; back: () => void }) {
  const documentId = metadata.id
  const [status, setStatus] = useState<ConnectionStatus>('connecting')
  const [saved, setSaved] = useState('Синхронизация…')
  const [role, setRole] = useState(metadata.role)
  const [panel, setPanel] = useState<'share' | 'history' | 'export' | null>(null)
  const [title, setTitle] = useState(metadata.title)
  const [error, setError] = useState('')
  // Один Y.Doc и одно соединение на открытый редактор, не на каждый рендер.
  const [session] = useState(() => {
    const document = new Y.Doc()
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const provider = new WebsocketProvider(
      `${protocol}//${window.location.host}/ws/documents`,
      documentId,
      document,
      { connect: false, params: { token: getAccessToken() || '', generation: String(metadata.generation) } },
    )
    // Имя и цвет курсора не определяют права пользователя.
    const colors = ['#2563eb', '#c026d3', '#059669', '#d97706']
    return {
      document,
      provider,
      user: {
        name: `Участник ${document.clientID.toString(16).slice(-4)}`,
        color: colors[document.clientID % colors.length],
      },
    }
  })

  const editor = useEditor({
    extensions: [
      // Историей отмены управляет Collaboration, стандартный undoRedo отключён.
      StarterKit.configure({ undoRedo: false, heading: { levels: [1, 2, 3] }, blockquote: false, code: false, codeBlock: false, horizontalRule: false, strike: false, underline: false, link: false }),
      // Все клиенты редактируют один XML-фрагмент с именем default.
      Collaboration.configure({ document: session.document, field: 'default' }),
      CollaborationCaret.configure({ provider: session.provider, user: session.user }),
    ],
    editable: role !== 'viewer',
    editorProps: {
      attributes: {
        class: 'document-editor',
        'aria-label': 'Содержимое документа',
        role: 'textbox',
        'aria-multiline': 'true',
      },
    },
  })

  useEffect(() => { editor?.setEditable(role !== 'viewer') }, [editor, role])

  useEffect(() => {
    // Подключаемся после монтирования; при уходе со страницы убираем соединение и Y.Doc.
    let control: WebSocket | null = null
    let reconnect: ReturnType<typeof setTimeout>
    let active = true
    const openControl = () => {
      if (!active || !navigator.onLine || control?.readyState === WebSocket.OPEN || control?.readyState === WebSocket.CONNECTING) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      control = new WebSocket(`${protocol}//${window.location.host}/ws/documents/${documentId}/status?token=${encodeURIComponent(getAccessToken() || '')}&generation=${metadata.generation}`)
      control.onmessage = (event) => {
        const data = JSON.parse(String(event.data)) as { status: string; role?: Document['role'] }
        if (data.role) setRole(data.role)
        if (data.status !== 'role_changed') setSaved(({ saved: 'Сохранено', unsaved: 'Есть несохранённые изменения', error: 'Ошибка сохранения' })[data.status] || 'Синхронизация…')
      }
      control.onclose = () => { if (active) { setSaved('Нет соединения'); reconnect = setTimeout(openControl, 2000) } }
    }
    const onStatus = ({ status: value }: { status: ConnectionStatus }) => {
      setStatus(value)
      if (value === 'connected') openControl()
      else setSaved('Нет соединения')
    }
    const onClose = (event: CloseEvent | null) => {
      if (event?.code === 4409) {
        session.provider.disconnect()
        window.alert('Восстановлена другая версия. Редактор будет перезагружен.')
        reload()
      } else if (event?.code === 4401) {
        setAccessToken(null)
        window.dispatchEvent(new Event('cowrite:logout'))
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
      setSaved('Нет соединения')
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
  }, [session, documentId, metadata.generation, reload])

  const labels = {
    connecting: 'Подключение…',
    connected: 'Соединение установлено',
    disconnected: 'Нет соединения',
  }

  return (
    <>
      <header className="editor-header">
        <div>
          <button className="brand text-button" onClick={back}>Cowrite</button>
          <input aria-label="Название документа" value={title} maxLength={200} readOnly={role !== 'owner'} onChange={(event) => setTitle(event.target.value)} onBlur={() => {
            if (role === 'owner' && title !== metadata.title) void api<Document>(`/documents/${documentId}`, { method: 'PATCH', body: JSON.stringify({ title }) }).catch((reason: Error) => setError(reason.message))
          }} />
        </div>
        <span className={`connection ${status}`} role="status">{status === 'connected' ? saved : labels[status]}</span>
        <div className="header-actions">
          {role === 'owner' && <button onClick={() => setPanel(panel === 'share' ? null : 'share')}>Доступ</button>}
          <button onClick={() => setPanel(panel === 'history' ? null : 'history')}>История</button>
          <button onClick={() => setPanel(panel === 'export' ? null : 'export')}>PDF</button>
        </div>
      </header>
      {error && <p role="alert">{error}</p>}
      {panel === 'share' && role === 'owner' && <Share document={{ ...metadata, role }} />}
      {panel === 'history' && <History document={{ ...metadata, role }} onRestore={reload} />}
      {panel === 'export' && <Export document={metadata} />}
      {role !== 'viewer' && <nav className="toolbar" aria-label="Форматирование текста">
        {/* focus возвращает выделение в редактор после нажатия кнопки панели. */}
        <button type="button" onClick={() => editor?.chain().focus().toggleBold().run()} aria-label="Жирный"><strong>Ж</strong></button>
        <button type="button" onClick={() => editor?.chain().focus().toggleItalic().run()} aria-label="Курсив"><em>К</em></button>
        {([1, 2, 3] as const).map((level) => (
          <button type="button" key={level} onClick={() => editor?.chain().focus().toggleHeading({ level }).run()} aria-label={`Заголовок ${level}`}>H{level}</button>
        ))}
        <button type="button" onClick={() => editor?.chain().focus().toggleBulletList().run()}>• Список</button>
        <button type="button" onClick={() => editor?.chain().focus().toggleOrderedList().run()}>1. Список</button>
      </nav>}
      <main className="paper"><EditorContent editor={editor} /></main>
    </>
  )
}

export function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [authenticated, setAuthenticated] = useState(Boolean(getAccessToken()))
  const [metadata, setMetadata] = useState<Document | null>(null)
  const [error, setError] = useState('')
  const [epoch, setEpoch] = useState(0)
  const navigate = useCallback((next: string) => {
    window.history.pushState(null, '', next)
    setMetadata(null); setError(''); setPath(next)
  }, [])
  const reload = useCallback(() => { setMetadata(null); setError(''); setEpoch((value) => value + 1) }, [])

  useEffect(() => {
    const logout = () => { setAuthenticated(false); setMetadata(null) }
    const pop = () => { setMetadata(null); setError(''); setPath(window.location.pathname) }
    window.addEventListener('cowrite:logout', logout)
    window.addEventListener('popstate', pop)
    return () => { window.removeEventListener('cowrite:logout', logout); window.removeEventListener('popstate', pop) }
  }, [])

  const finishLogin = useCallback(() => {
    setAuthenticated(true)
    if (window.location.pathname === '/auth/callback') navigate('/')
  }, [navigate])
  const match = /^\/documents\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/?$/i.exec(path)
  const documentId = match?.[1]
  useEffect(() => {
    if (!authenticated || !documentId) return
    let active = true
    void api<Document>(`/documents/${documentId}`).then((data) => { if (active) setMetadata(data) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [authenticated, documentId, epoch])
  if (path === '/auth/callback') return <OAuthCallback onComplete={finishLogin} />
  if (!authenticated) return <Auth onComplete={finishLogin} />
  const logout = () => { setAccessToken(null); setAuthenticated(false); setMetadata(null) }
  if (path === '/') return <><header className="editor-header"><span className="brand">Cowrite</span><button onClick={logout}>Выйти</button></header><Documents open={(id) => navigate(`/documents/${id}`)} /></>
  if (documentId) {
    if (error) return <main className="auth-state"><p role="alert">{error}</p><button onClick={() => navigate('/')}>К документам</button></main>
    if (!metadata) return <main className="auth-state" role="status">Загрузка…</main>
    return <Editor key={`${metadata.id}-${metadata.generation}-${epoch}`} metadata={metadata} reload={reload} back={() => navigate('/')} />
  }

  return (
    <main className="auth-state">
      <h1>Страница не найдена</h1>
      <a href="/">Открыть редактор</a>
    </main>
  )
}
