import { useEffect, useState } from 'react'
import { api, type DocumentMeta } from './api'
import { formatDateTime, roleLabels } from './labels'
import { PAGE_SIZE, Pagination } from './Pagination'

export function Documents({ open }: { open: (id: string) => void }) {
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void api<DocumentMeta[]>(`/documents?limit=${PAGE_SIZE}&offset=${offset}`).then((result) => { if (active) setDocuments(result) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [offset])
  async function create() {
    setBusy(true)
    try { open((await api<DocumentMeta>('/documents', { method: 'POST', body: '{}' })).id) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось создать документ') }
    finally { setBusy(false) }
  }
  async function remove(doc: DocumentMeta) {
    if (!window.confirm(`Удалить «${doc.title}»?`)) return
    try {
      await api(`/documents/${doc.id}`, { method: 'DELETE' })
      setDocuments((current) => current.filter((item) => item.id !== doc.id))
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Не удалось удалить документ') }
  }
  return <main className="document-list">
    <div className="section-header"><h1>Документы</h1><button disabled={busy} onClick={() => { void create() }}>Новый документ</button></div>
    {error && <p role="alert">{error}</p>}
    {documents.map((doc) => <article className="document-row" key={doc.id}>
      <button className="text-button document-title" onClick={() => open(doc.id)}>{doc.title}</button>
      <span>{roleLabels[doc.role]}</span>
      <time dateTime={doc.updated_at}>{formatDateTime(doc.updated_at)}</time>
      {doc.role === 'owner' && <button onClick={() => { void remove(doc) }} aria-label={`Удалить ${doc.title}`}>Удалить</button>}
    </article>)}
    <Pagination offset={offset} count={documents.length} onChange={setOffset} />
  </main>
}
