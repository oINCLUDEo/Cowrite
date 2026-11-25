import { useEffect, useState } from 'react'
import { api, type DocumentMeta } from './api'
import { PlusIcon } from './icons'
import { formatDateTime, roleLabels } from './labels'
import { PAGE_SIZE, Pagination } from './Pagination'

export function Documents({ open }: { open: (id: string) => void }) {
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [error, setError] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    let active = true
    void api<DocumentMeta[]>(`/documents?limit=${PAGE_SIZE}&offset=${offset}`).then((result) => { if (active) { setDocuments(result); setLoaded(true) } }).catch((reason: Error) => { if (active) setError(reason.message) })
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
  // Пустое состояние только после ответа сервера, иначе оно мигало бы на время загрузки.
  const empty = loaded && !error && offset === 0 && documents.length === 0
  const newButton = <button className="btn-primary new-document" disabled={busy} onClick={() => { void create() }}><PlusIcon />Новый документ</button>
  // Пустой список: заголовок страницы и есть сообщение, а 3D-лист — сама кнопка, как плитка «Пустой файл» в Google Docs.
  if (empty) return <main className="document-list">
    <section className="empty-hero">
      <h1>Документы</h1>
      <p>Пока здесь пусто</p>
      <div className="tile-row">
        <button className="new-tile" disabled={busy} onClick={() => { void create() }}>
          <span className="new-tile-art"><img src="/file-3d.webp" alt="" width={150} height={150} /></span>
          <span className="new-tile-label"><PlusIcon />Новый документ</span>
        </button>
        {/* Призрачные заготовки на месте будущих документов: заполняют ряд, экранным чтецам не нужны. */}
        {[1, 2, 3].map((n) => <span className="ghost-tile" aria-hidden="true" key={n}><i /><i /><i /><i /></span>)}
      </div>
    </section>
  </main>
  return <main className="document-list">
    <div className="section-header"><h1>Документы</h1>{newButton}</div>
    {error && <p role="alert">{error}</p>}
    {documents.map((doc) => <article className="document-row" key={doc.id}>
      <button className="text-button document-title" onClick={() => open(doc.id)}>{doc.title}</button>
      <span>{roleLabels[doc.role]}</span>
      <time dateTime={doc.updated_at}>{formatDateTime(doc.updated_at)}</time>
      {doc.role === 'owner' && <button className="btn-danger" onClick={() => { void remove(doc) }} aria-label={`Удалить ${doc.title}`}>Удалить</button>}
    </article>)}
    {(offset > 0 || documents.length >= PAGE_SIZE) && <Pagination offset={offset} count={documents.length} onChange={setOffset} />}
  </main>
}
