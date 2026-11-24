import { useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCaret from '@tiptap/extension-collaboration-caret'
import { History, Share } from './Panels'
import { api, type DocumentMeta, type Role } from './api'
import { BackIcon, DownloadIcon, HistoryIcon, MoreIcon, ShareIcon } from './icons'
import { connectionLabels } from './labels'
import { usePdfExport } from './pdf'
import { useCollabConnection, useCollabSession, type ConnectionStatus } from './useCollab'

type Panel = 'share' | 'history' | null

export function Editor({ metadata, reload, back }: { metadata: DocumentMeta; reload: () => void; back: () => void }) {
  const documentId = metadata.id
  const collab = useCollabSession(metadata)
  const { session, status, saved, role, error, setError } = collab
  const [panel, setPanel] = useState<Panel>(null)
  const [title, setTitle] = useState(metadata.title)
  // Файл называется так, как документ назван на экране сейчас.
  const pdf = usePdfExport(documentId, title)

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

  useCollabConnection(collab, metadata, reload)
  // «Доступ» видит только владелец: если роль сменилась, панель не показывается, как и раньше.
  const side = panel === 'history' || (panel === 'share' && role === 'owner')
  const close = () => setPanel(null)

  return (
    <>
      <EditorHeader back={back} documentId={documentId} metadata={metadata} title={title} setTitle={setTitle} role={role} setError={setError} status={status} saved={saved} panel={panel} setPanel={setPanel} exporting={pdf.busy} onExport={() => { void pdf.start() }} />
      {error && <p role="alert">{error}</p>}
      {/* На широком экране ход экспорта виден на самой кнопке, на телефоне — этой строкой: кнопка спрятана в меню. */}
      {pdf.busy && <p className="page-note pdf-progress" role="status">Готовим PDF…</p>}
      {pdf.error && <p className="page-note" role="alert">{pdf.error}</p>}
      {/* Обёртка есть всегда: при открытии боковой панели редактор не пересоздаётся, а встаёт левее неё. */}
      <div className={side ? 'workspace with-side' : 'workspace'}>
        <div className="workspace-main">
          {role !== 'viewer' && <EditorToolbar editor={editor} />}
          <main className="paper"><EditorContent editor={editor} /></main>
        </div>
        {side && <>
          <div className="scrim" onClick={close} />
          {panel === 'history'
            ? <History doc={{ ...metadata, role }} onRestore={reload} onClose={close} />
            : <Share doc={{ ...metadata, role }} onClose={close} />}
        </>}
      </div>
    </>
  )
}

type HeaderProps = {
  back: () => void; documentId: string; metadata: DocumentMeta; title: string; setTitle: (title: string) => void
  role: Role; setError: (error: string) => void; status: ConnectionStatus; saved: string; panel: Panel; setPanel: (panel: Panel) => void
  exporting: boolean; onExport: () => void
}

// Шапка и панель объявлены на уровне модуля: внутри Editor они пересоздавались бы на каждом рендере,
// и поле названия теряло бы фокус после каждой буквы.
function EditorHeader({ back, documentId, metadata, title, setTitle, role, setError, status, saved, panel, setPanel, exporting, onExport }: HeaderProps) {
  const pdfLabel = exporting ? 'Готовим PDF…' : 'PDF'
  const toggle = (next: Exclude<Panel, null>) => setPanel(panel === next ? null : next)
  const pressed = (name: Panel) => (panel === name ? ' on' : '')
  return (
    <header className="doc-header">
      <button className="icon-button" onClick={back} aria-label="К документам" title="К документам"><BackIcon /></button>
      <div className="doc-title">
        {role === 'owner'
          ? <input className="title-input" aria-label="Название документа" value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} onBlur={() => {
            if (title !== metadata.title) void api<DocumentMeta>(`/documents/${documentId}`, { method: 'PATCH', body: JSON.stringify({ title }) }).catch((reason: Error) => setError(reason.message))
          }} />
          : <h1 className="title-text">{title}</h1>}
        <span className={`connection ${status}`} role="status">{status === 'connected' ? saved : connectionLabels[status]}</span>
      </div>
      <div className="doc-actions">
        <button className={`btn-ghost wide-only${pressed('history')}`} aria-expanded={panel === 'history'} onClick={() => toggle('history')}><HistoryIcon />История</button>
        <button className="btn-ghost wide-only" disabled={exporting} aria-busy={exporting} onClick={onExport}><DownloadIcon />{pdfLabel}</button>
        {role === 'owner' && <button className={`btn-primary share${pressed('share')}`} aria-expanded={panel === 'share'} onClick={() => toggle('share')}><ShareIcon /><span className="label">Поделиться</span></button>}
        {/* На телефоне «История» и «PDF» уходят в меню; Popover сам закрывается по Esc и клику мимо. */}
        <button className="icon-button narrow-only" popoverTarget="doc-more" aria-label="Ещё" title="Ещё"><MoreIcon /></button>
        <div id="doc-more" className="menu" popover="auto">
          <button popoverTarget="doc-more" popoverTargetAction="hide" onClick={() => toggle('history')}><HistoryIcon />История</button>
          <button popoverTarget="doc-more" popoverTargetAction="hide" disabled={exporting} onClick={onExport}><DownloadIcon />{pdfLabel}</button>
        </div>
      </div>
    </header>
  )
}

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  return (
    <nav className="toolbar" aria-label="Форматирование текста">
      {/* focus возвращает выделение в редактор после нажатия кнопки панели. */}
      <button type="button" onClick={() => editor?.chain().focus().toggleBold().run()} aria-label="Жирный"><strong>Ж</strong></button>
      <button type="button" onClick={() => editor?.chain().focus().toggleItalic().run()} aria-label="Курсив"><em>К</em></button>
      {([1, 2, 3] as const).map((level) => (
        <button type="button" key={level} onClick={() => editor?.chain().focus().toggleHeading({ level }).run()} aria-label={`Заголовок ${level}`}>H{level}</button>
      ))}
      <button type="button" onClick={() => editor?.chain().focus().toggleBulletList().run()}>• Список</button>
      <button type="button" onClick={() => editor?.chain().focus().toggleOrderedList().run()}>1. Список</button>
    </nav>
  )
}
