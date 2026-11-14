import { useEffect, useState } from 'react'
import { api, type Document } from './api'

export function Documents({ open }: { open: (id: string) => void }) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void api<Document[]>(`/documents?limit=20&offset=${offset}`).then((result) => { if (active) setDocuments(result) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [offset])
  async function create() {
    setBusy(true)
    try { open((await api<Document>('/documents', { method: 'POST', body: '{}' })).id) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось создать документ') }
    finally { setBusy(false) }
  }
  async function remove(document: Document) {
    if (!window.confirm(`Удалить «${document.title}»?`)) return
    try {
      await api(`/documents/${document.id}`, { method: 'DELETE' })
      setDocuments((current) => current.filter((item) => item.id !== document.id))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось удалить документ') }
  }
  return <main className="document-list">
    <div className="section-header"><h1>Документы</h1><button disabled={busy} onClick={() => { void create() }}>Новый документ</button></div>
    {error && <p role="alert">{error}</p>}
    {documents.map((document) => <article className="document-row" key={document.id}>
      <button className="text-button document-title" onClick={() => open(document.id)}>{document.title}</button>
      <span>{({ owner: 'Владелец', editor: 'Редактор', viewer: 'Читатель' })[document.role]}</span>
      <time dateTime={document.updated_at}>{new Date(document.updated_at).toLocaleString('ru-RU')}</time>
      {document.role === 'owner' && <button onClick={() => { void remove(document) }} aria-label={`Удалить ${document.title}`}>Удалить</button>}
    </article>)}
    <div className="pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Назад</button><button disabled={documents.length < 20} onClick={() => setOffset(offset + 20)}>Далее</button></div>
  </main>
}
