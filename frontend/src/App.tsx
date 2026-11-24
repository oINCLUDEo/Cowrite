import { useCallback, useEffect, useState } from 'react'
import { OAuthCallback } from './OAuthCallback'
import { Auth } from './Auth'
import { Documents } from './Documents'
import { Editor } from './Editor'
import { api, type DocumentMeta } from './api'
import { getAccessToken, logout } from './session'

export function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [authenticated, setAuthenticated] = useState(Boolean(getAccessToken()))
  const [metadata, setMetadata] = useState<DocumentMeta | null>(null)
  const [error, setError] = useState('')
  const [epoch, setEpoch] = useState(0)
  const navigate = useCallback((next: string) => {
    window.history.pushState(null, '', next)
    setMetadata(null); setError(''); setPath(next)
  }, [])
  const reload = useCallback(() => { setMetadata(null); setError(''); setEpoch((value) => value + 1) }, [])

  useEffect(() => {
    const onLogout = () => { setAuthenticated(false); setMetadata(null) }
    const pop = () => { setMetadata(null); setError(''); setPath(window.location.pathname) }
    window.addEventListener('cowrite:logout', onLogout)
    window.addEventListener('popstate', pop)
    return () => { window.removeEventListener('cowrite:logout', onLogout); window.removeEventListener('popstate', pop) }
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
    void api<DocumentMeta>(`/documents/${documentId}`).then((data) => { if (active) setMetadata(data) }).catch((reason: Error) => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [authenticated, documentId, epoch])
  if (path === '/auth/callback') return <OAuthCallback onComplete={finishLogin} />
  if (!authenticated) return <Auth onComplete={finishLogin} />
  if (path === '/') return <><header className="editor-header"><span className="brand">Cowrite</span><button className="btn-ghost" onClick={logout}>Выйти</button></header><Documents open={(id) => navigate(`/documents/${id}`)} /></>
  if (documentId) {
    if (error) return <main className="auth-state"><p role="alert">{error}</p><button className="btn-primary" onClick={() => navigate('/')}>К документам</button></main>
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
