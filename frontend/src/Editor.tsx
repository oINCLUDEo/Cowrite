import { useEffect, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCaret from '@tiptap/extension-collaboration-caret'
import { Export, History, Share } from './Panels'
import { api, type DocumentMeta, type Role } from './api'
import { connectionLabels } from './labels'
import { useCollabConnection, useCollabSession, type ConnectionStatus } from './useCollab'

type Panel = 'share' | 'history' | 'export' | null

export function Editor({ metadata, reload, back }: { metadata: DocumentMeta; reload: () => void; back: () => void }) {
  const documentId = metadata.id
  const collab = useCollabSession(metadata)
  const { session, status, saved, role, error, setError } = collab
  const [panel, setPanel] = useState<Panel>(null)
  const [title, setTitle] = useState(metadata.title)

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

  return (
    <>
      <EditorHeader back={back} documentId={documentId} metadata={metadata} title={title} setTitle={setTitle} role={role} setError={setError} status={status} saved={saved} panel={panel} setPanel={setPanel} />
      {error && <p role="alert">{error}</p>}
      {panel === 'share' && role === 'owner' && <Share doc={{ ...metadata, role }} />}
      {panel === 'history' && <History doc={{ ...metadata, role }} onRestore={reload} />}
      {panel === 'export' && <Export doc={metadata} />}
      {role !== 'viewer' && <EditorToolbar editor={editor} />}
      <main className="paper"><EditorContent editor={editor} /></main>
    </>
  )
}

type HeaderProps = {
  back: () => void; documentId: string; metadata: DocumentMeta; title: string; setTitle: (title: string) => void
  role: Role; setError: (error: string) => void; status: ConnectionStatus; saved: string; panel: Panel; setPanel: (panel: Panel) => void
}

// Шапка и панель объявлены на уровне модуля: внутри Editor они пересоздавались бы на каждом рендере,
// и поле названия теряло бы фокус после каждой буквы.
function EditorHeader({ back, documentId, metadata, title, setTitle, role, setError, status, saved, panel, setPanel }: HeaderProps) {
  return (
    <header className="editor-header">
      <div>
        <button className="brand text-button" onClick={back}>Cowrite</button>
        <input aria-label="Название документа" value={title} maxLength={200} readOnly={role !== 'owner'} onChange={(event) => setTitle(event.target.value)} onBlur={() => {
          if (role === 'owner' && title !== metadata.title) void api<DocumentMeta>(`/documents/${documentId}`, { method: 'PATCH', body: JSON.stringify({ title }) }).catch((reason: Error) => setError(reason.message))
        }} />
      </div>
      <span className={`connection ${status}`} role="status">{status === 'connected' ? saved : connectionLabels[status]}</span>
      <div className="header-actions">
        {role === 'owner' && <button onClick={() => setPanel(panel === 'share' ? null : 'share')}>Доступ</button>}
        <button onClick={() => setPanel(panel === 'history' ? null : 'history')}>История</button>
        <button onClick={() => setPanel(panel === 'export' ? null : 'export')}>PDF</button>
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
