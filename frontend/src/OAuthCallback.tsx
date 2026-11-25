import { useEffect, useState } from 'react'
import { setAccessToken } from './session'

export function OAuthCallback({ onComplete }: { onComplete: () => void }) {
  const [error, setError] = useState(false)

  useEffect(() => {
    const code = new URLSearchParams(window.location.hash.slice(1)).get('code')
    // Убираем одноразовый код из адресной строки до сетевых запросов.
    window.history.replaceState(null, '', '/auth/callback')
    let active = true
    async function exchange() {
      try {
        if (!code) throw new Error('Missing exchange code')
        const response = await fetch('/api/auth/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ code }),
        })
        const data: unknown = await response.json()
        if (!response.ok || typeof data !== 'object' || data === null ||
          !('access_token' in data) || typeof data.access_token !== 'string' ||
          !data.access_token) throw new Error('Exchange failed')
        if (active) {
          setAccessToken(data.access_token)
          onComplete()
        }
      } catch {
        if (active) setError(true)
      }
    }
    void exchange()
    return () => { active = false }
  }, [onComplete])

  return (
    <main className="auth-state">
      <h1>Cowrite</h1>
      {error ? <><p role="alert">Не удалось войти</p><a href="/api/auth/github/login">Повторить</a></> :
        <p role="status">Вход…</p>}
    </main>
  )
}
