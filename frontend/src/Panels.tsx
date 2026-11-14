import { useEffect, useState } from 'react'
import { api, apiResponse, type Document } from './api'

type Member = { user_id: string; email: string; display_name: string; role: 'editor' | 'viewer'; notification: string }
type Version = { id: string; created_at: string; kind: string; source_revision: number }

export function Share({ document }: { document: Document }) {
  const [members, setMembers] = useState<Member[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const refresh = () => api<Member[]>(`/documents/${document.id}/members`).then(setMembers)
  useEffect(() => {
    let active = true
    void api<Member[]>(`/documents/${document.id}/members`).then((items) => { if (active) setMembers(items) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [document.id])
  return <section className="panel" aria-label="Доступ"><h2>Доступ</h2>
    <form onSubmit={(event) => {
      event.preventDefault()
      const data = new FormData(event.currentTarget)
      void api<Member>(`/documents/${document.id}/members`, { method: 'POST', body: JSON.stringify({ email: data.get('email'), role: data.get('role') }) })
        .then(async (member) => { setNotice(member.notification === 'queue_failed' ? 'Доступ предоставлен, письмо не поставлено в очередь' : 'Доступ предоставлен'); await refresh() })
        .catch((reason: Error) => setError(reason.message))
    }}>
      <input type="email" name="email" placeholder="Email" aria-label="Email участника" required />
      <select name="role" aria-label="Роль участника"><option value="editor">Редактор</option><option value="viewer">Читатель</option></select>
      <button>Предоставить доступ</button>
    </form>
    {members.map((member) => <div className="member-row" key={member.user_id}><span>{member.email}</span><span>{member.role === 'editor' ? 'Редактор' : 'Читатель'}</span>
      <button onClick={() => { void api(`/documents/${document.id}/members/${member.user_id}`, { method: 'DELETE' }).then(refresh).catch((reason: Error) => setError(reason.message)) }}>Убрать</button>
    </div>)}
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>
}

export function History({ document, onRestore }: { document: Document; onRestore: () => void }) {
  const [versions, setVersions] = useState<Version[]>([])
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const refresh = () => api<Version[]>(`/documents/${document.id}/versions?limit=20&offset=${offset}`).then(setVersions)
  useEffect(() => {
    let active = true
    void api<Version[]>(`/documents/${document.id}/versions?limit=20&offset=${offset}`).then((items) => { if (active) setVersions(items) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [document.id, offset])
  return <section className="panel" aria-label="История"><h2>История</h2>
    {document.role !== 'viewer' && <button onClick={() => { void api(`/documents/${document.id}/versions`, { method: 'POST' }).then(refresh).catch((reason: Error) => setError(reason.message)) }}>Сохранить версию</button>}
    {versions.map((version) => <div className="member-row" key={version.id}><time>{new Date(version.created_at).toLocaleString('ru-RU')}</time><span>{({ manual: 'Ручная', scheduled: 'Автоматическая', export: 'Экспорт' })[version.kind]} · {version.source_revision}</span>
      {document.role !== 'viewer' && <button onClick={() => {
        if (!window.confirm('Восстановить версию? Текущие соединения будут сброшены, несинхронизированные правки потеряются.')) return
        void api(`/documents/${document.id}/versions/${version.id}/restore`, { method: 'POST' }).then(onRestore).catch((reason: Error) => setError(reason.message))
      }}>Восстановить</button>}
    </div>)}
    <div className="pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Назад</button><button disabled={versions.length < 20} onClick={() => setOffset(offset + 20)}>Далее</button></div>
    {error && <p role="alert">{error}</p>}
  </section>
}

export function Export({ document }: { document: Document }) {
  const [jobId, setJobId] = useState<string | null>(null)
  const [state, setState] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!jobId) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const result = await api<{ status: string; error_code: string | null }>(`/exports/${jobId}`)
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
      anchor.href = url; anchor.download = `${document.title}.pdf`; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка скачивания') }
  }
  return <section className="panel" aria-label="Экспорт"><h2>PDF</h2>
    <button disabled={busy || state === 'queued' || state === 'running'} onClick={() => {
      setBusy(true); setError('')
      void api<{ task_id: string }>(`/documents/${document.id}/export`, { method: 'POST' }).then((result) => { setState('queued'); setJobId(result.task_id) }).catch((reason: Error) => setError(reason.message)).finally(() => setBusy(false))
    }}>Создать PDF</button>
    {(state === 'queued' || state === 'running') && <p role="status">Подготовка…</p>}
    {state === 'succeeded' && <button onClick={() => { void download() }}>Скачать PDF</button>}
    {error && <p role="alert">{error}</p>}
  </section>
}
