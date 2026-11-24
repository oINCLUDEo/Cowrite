import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { api, apiResponse, type DocumentMeta, type ExportAccepted, type ExportJob, type ExportStatus, type Member, type Version } from './api'
import { BookmarkPlusIcon, CloseIcon } from './icons'
import { formatDay, formatTime, roleLabels, versionKindLabels } from './labels'
import { PAGE_SIZE, Pagination } from './Pagination'

// Правая панель (на телефоне нижний лист) для «Доступа» и «Истории»: заголовок, свои действия, закрытие по «×» и Esc.
function SidePanel({ title, actions, onClose, children }: { title: string; actions?: ReactNode; onClose: () => void; children: ReactNode }) {
  return <aside className="side-panel" aria-label={title} onKeyDown={(event) => { if (event.key === 'Escape') onClose() }}>
    <div className="side-head">
      <h2>{title}</h2>
      {actions}
      <button className="icon-button" onClick={onClose} aria-label="Закрыть" title="Закрыть"><CloseIcon /></button>
    </div>
    <div className="side-body">{children}</div>
  </aside>
}

export function Share({ doc, onClose }: { doc: DocumentMeta; onClose: () => void }) {
  const [members, setMembers] = useState<Member[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const refresh = () => api<Member[]>(`/documents/${doc.id}/members`).then(setMembers)
  useEffect(() => {
    let active = true
    void api<Member[]>(`/documents/${doc.id}/members`).then((items) => { if (active) setMembers(items) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [doc.id])
  return <SidePanel title="Доступ к документу" onClose={onClose}>
    <form className="share-form" onSubmit={(event) => {
      event.preventDefault()
      const data = new FormData(event.currentTarget)
      void api<Member>(`/documents/${doc.id}/members`, { method: 'POST', body: JSON.stringify({ email: data.get('email'), role: data.get('role') }) })
        .then(async (member) => { setNotice(member.notification === 'queue_failed' ? 'Доступ предоставлен, письмо не поставлено в очередь' : 'Доступ предоставлен'); await refresh() })
        .catch((reason: Error) => setError(reason.message))
    }}>
      <input type="email" name="email" placeholder="Email" aria-label="Email участника" required />
      <div>
        <select name="role" aria-label="Роль участника"><option value="editor">{roleLabels.editor}</option><option value="viewer">{roleLabels.viewer}</option></select>
        <button className="btn-primary">Предоставить доступ</button>
      </div>
    </form>
    {notice && <p className="side-note" role="status">{notice}</p>}{error && <p className="side-note" role="alert">{error}</p>}
    {members.length > 0 && <h3 className="side-subhead">Участники</h3>}
    {members.map((member) => <div className="member" key={member.user_id}>
      <div><b>{member.display_name}</b><small>{member.email}</small></div>
      <span className="member-role">{roleLabels[member.role]}</span>
      <button onClick={() => { void api(`/documents/${doc.id}/members/${member.user_id}`, { method: 'DELETE' }).then(refresh).catch((reason: Error) => setError(reason.message)) }} className="btn-danger" aria-label={`Убрать ${member.email}`}>Убрать</button>
    </div>)}
  </SidePanel>
}

// Лента версий справа от документа (на телефоне нижним листом), как история версий в Google Docs.
export function History({ doc, onRestore, onClose }: { doc: DocumentMeta; onRestore: () => void; onClose: () => void }) {
  const [versions, setVersions] = useState<Version[]>([])
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const refresh = () => api<Version[]>(`/documents/${doc.id}/versions?limit=${PAGE_SIZE}&offset=${offset}`).then(setVersions)
  useEffect(() => {
    let active = true
    void api<Version[]>(`/documents/${doc.id}/versions?limit=${PAGE_SIZE}&offset=${offset}`).then((items) => { if (active) setVersions(items) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [doc.id, offset])
  const save = () => { void api(`/documents/${doc.id}/versions`, { method: 'POST' }).then(refresh).catch((reason: Error) => setError(reason.message)) }
  const restore = (version: Version) => {
    if (!window.confirm('Восстановить версию? Текущие соединения будут сброшены, несинхронизированные правки потеряются.')) return
    void api(`/documents/${doc.id}/versions/${version.id}/restore`, { method: 'POST' }).then(onRestore).catch((reason: Error) => setError(reason.message))
  }
  const saveButton = doc.role !== 'viewer' && <button className="icon-button" onClick={save} aria-label="Сохранить версию" title="Сохранить версию"><BookmarkPlusIcon /></button>
  return <SidePanel title="История версий" actions={saveButton} onClose={onClose}>
    {versions.map((version, index) => {
      const day = formatDay(version.created_at)
      const time = formatTime(version.created_at)
      return <Fragment key={version.id}>
        {(index === 0 || day !== formatDay(versions[index - 1].created_at)) && <h3 className="side-subhead">{day}</h3>}
        <div className="version" title={`Ревизия ${version.source_revision}`}>
          <div><time dateTime={version.created_at}>{time}</time><span>{versionKindLabels[version.kind]}</span></div>
          {doc.role !== 'viewer' && <button className="btn-ghost restore" onClick={() => restore(version)} aria-label={`Восстановить версию от ${time}`}>Восстановить</button>}
        </div>
      </Fragment>
    })}
    {(offset > 0 || versions.length >= PAGE_SIZE) && <Pagination offset={offset} count={versions.length} onChange={setOffset} />}
    {error && <p role="alert">{error}</p>}
  </SidePanel>
}

export function Export({ doc }: { doc: DocumentMeta }) {
  const [jobId, setJobId] = useState<string | null>(null)
  const [state, setState] = useState<ExportStatus | ''>('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!jobId) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const result = await api<ExportJob>(`/exports/${jobId}`)
        if (!active) return
        setState(result.status)
        if (result.status === 'failed') setError('Не удалось создать PDF')
        else if (result.status !== 'succeeded') timer = setTimeout(() => { void poll() }, 2000)
      } catch (reason) {
        if (active) {
          setState('failed')
          setError(reason instanceof Error ? reason.message : 'Ошибка экспорта')
        }
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [jobId])
  async function download() {
    try {
      const response = await apiResponse(`/exports/${jobId}/file`)
      const url = URL.createObjectURL(await response.blob())
      const anchor = window.document.createElement('a')
      anchor.href = url; anchor.download = `${doc.title}.pdf`; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка скачивания') }
  }
  return <section className="panel" aria-label="Экспорт"><h2>PDF</h2>
    <button disabled={busy || state === 'queued' || state === 'running'} onClick={() => {
      setBusy(true); setError('')
      void api<ExportAccepted>(`/documents/${doc.id}/export`, { method: 'POST' }).then((result) => { setState('queued'); setJobId(result.task_id) }).catch((reason: Error) => setError(reason.message)).finally(() => setBusy(false))
    }}>Создать PDF</button>
    {(state === 'queued' || state === 'running') && <p role="status">Подготовка…</p>}
    {state === 'succeeded' && <button className="btn-primary" onClick={() => { void download() }}>Скачать PDF</button>}
    {error && <p role="alert">{error}</p>}
  </section>
}
