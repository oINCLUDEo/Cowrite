import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { EditorContent, useEditor, useEditorState } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCaret from '@tiptap/extension-collaboration-caret'
import { Placeholder } from '@tiptap/extensions'
import { History, Share } from './Panels'
import { api, type DocumentMeta, type Role } from './api'
import { AlertIcon, BackIcon, BulletListIcon, CloudCheckIcon, CloudIcon, CloudOffIcon, CloudUploadIcon, DownloadIcon, HistoryIcon, MoreIcon, OrderedListIcon, ShareIcon } from './icons'
import { saveStateLabels, type SaveState } from './labels'
import { usePdfExport } from './pdf'
import { useCollabConnection, useCollabSession, type ConnectionStatus } from './useCollab'

type Panel = 'share' | 'history' | null

// Иконка статуса сохранения: облачко по состоянию, как в Google Docs.
const saveStateIcons: Record<SaveState, ReactNode> = {
  connecting: <CloudIcon />, syncing: <CloudUploadIcon />, unsaved: <CloudUploadIcon />,
  saved: <CloudCheckIcon />, offline: <CloudOffIcon />, error: <AlertIcon />,
}

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
      // Подсказка в пустом документе; читателю не показывается (showOnlyWhenEditable по умолчанию).
      Placeholder.configure({ placeholder: 'Начните писать' }),
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
  role: Role; setError: (error: string) => void; status: ConnectionStatus; saved: SaveState; panel: Panel; setPanel: (panel: Panel) => void
  exporting: boolean; onExport: () => void
}

// Шапка и панель объявлены на уровне модуля: внутри Editor они пересоздавались бы на каждом рендере,
// и поле названия теряло бы фокус после каждой буквы.
function EditorHeader({ back, documentId, metadata, title, setTitle, role, setError, status, saved, panel, setPanel, exporting, onExport }: HeaderProps) {
  const pdfLabel = exporting ? 'Готовим PDF…' : 'PDF'
  // Без CRDT-соединения сохранение невозможно, иначе показываем последнее состояние из /status.
  const state: SaveState = status === 'connected' ? saved : status === 'connecting' ? 'connecting' : 'offline'
  const [stateText, stateHint] = saveStateLabels[state]
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
        <span className={`save-status ${state}`} role="status" title={stateHint}>{saveStateIcons[state]}{stateText}</span>
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

// Без фокуса на mousedown выделение остаётся в редакторе: курсор не мигает у соавторов, а ввод не уходит в кнопку.
const keepFocus = (event: MouseEvent) => event.preventDefault()

function EditorToolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  // Оформление под курсором: стиль абзаца в списке, нажатые «Ж», «К» и списки.
  const active = useEditorState({
    editor,
    selector: ({ editor: current }) => ({
      bold: current?.isActive('bold') ?? false,
      italic: current?.isActive('italic') ?? false,
      bullet: current?.isActive('bulletList') ?? false,
      ordered: current?.isActive('orderedList') ?? false,
      level: ([1, 2, 3] as const).find((level) => current?.isActive('heading', { level })) ?? 0,
    }),
  })
  return (
    <nav className="toolbar" aria-label="Форматирование текста">
      <div className="notch">
        <select aria-label="Стиль текста" value={active.level} disabled={!editor} onChange={(event) => {
          const level = Number(event.target.value) as 0 | 1 | 2 | 3
          if (level) editor?.chain().focus().setHeading({ level }).run()
          else editor?.chain().focus().setParagraph().run()
        }}>
          <option value={0}>Обычный текст</option>
          <option value={1}>Заголовок 1</option>
          <option value={2}>Заголовок 2</option>
          <option value={3}>Заголовок 3</option>
        </select>
        <span className="toolbar-gap" />
        <button type="button" className="icon-button" onMouseDown={keepFocus} aria-pressed={active.bold} onClick={() => editor?.chain().focus().toggleBold().run()} aria-label="Жирный" title="Жирный, Ctrl+B"><strong>Ж</strong></button>
        <button type="button" className="icon-button" onMouseDown={keepFocus} aria-pressed={active.italic} onClick={() => editor?.chain().focus().toggleItalic().run()} aria-label="Курсив" title="Курсив, Ctrl+I"><em>К</em></button>
        <span className="toolbar-gap" />
        <button type="button" className="icon-button" onMouseDown={keepFocus} aria-pressed={active.bullet} onClick={() => editor?.chain().focus().toggleBulletList().run()} aria-label="Маркированный список" title="Маркированный список"><BulletListIcon /></button>
        <button type="button" className="icon-button" onMouseDown={keepFocus} aria-pressed={active.ordered} onClick={() => editor?.chain().focus().toggleOrderedList().run()} aria-label="Нумерованный список" title="Нумерованный список"><OrderedListIcon /></button>
      </div>
    </nav>
  )
}
