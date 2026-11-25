import { useState, type FormEvent } from 'react'
import { api, type TokenResponse, type User } from './api'
import { AlertIcon, LogoMark, Wordmark } from './icons'
import { setAccessToken } from './session'

// Сервер отвечает по-английски; на экране входа показываем по-русски.
const authErrors: Record<string, string> = {
  'Invalid email or password': 'Неверный email или пароль',
  'Email is already registered': 'Этот email уже зарегистрирован',
}

export function Auth({ onComplete }: { onComplete: () => void }) {
  const [register, setRegister] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const email = String(form.get('email'))
    const password = String(form.get('password'))
    setBusy(true)
    setError('')
    try {
      if (register) {
        await api<User>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, display_name: form.get('name') }) })
        // Аккаунт уже создан: при сбое входа повторяем вход, не регистрацию.
        setRegister(false)
      }
      const result = await api<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
      setAccessToken(result.access_token)
      onComplete()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Не удалось войти'
      setError(authErrors[message] ?? message)
    }
    finally { setBusy(false) }
  }
  return <main className="auth-page">
    <div className="auth-card">
      <div className="logo"><LogoMark />Cowrite</div>
      <h1 className="two-tone">{register ? 'Новый аккаунт' : 'Вход в аккаунт'} <span>Пишите вместе с командой</span></h1>
      <form onSubmit={(event) => { void submit(event) }} className="auth-form">
        {register && <div className="field">
          <label htmlFor="auth-name">Имя</label>
          <input id="auth-name" name="name" autoComplete="name" required maxLength={80} />
        </div>}
        <div className="field">
          <label htmlFor="auth-email">Email</label>
          <input id="auth-email" name="email" type="email" placeholder="name@example.com" autoComplete="email" required maxLength={254} />
        </div>
        <div className="field">
          <label htmlFor="auth-password">Пароль</label>
          <input id="auth-password" name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} minLength={12} maxLength={128} required aria-describedby={register ? 'auth-password-hint' : undefined} />
          {register && <span className="hint" id="auth-password-hint">Не короче 12 символов</span>}
        </div>
        {error && <p className="form-error" role="alert"><AlertIcon />{error}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>{register ? 'Зарегистрироваться' : 'Войти'}</button>
        <div className="or">или</div>
        <a className="github-button" href="/api/auth/github/login">
          <svg aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 .75a11.25 11.25 0 0 0-3.558 21.923c.563.104.77-.244.77-.542 0-.267-.01-.974-.015-1.912-3.13.68-3.79-1.508-3.79-1.508-.512-1.3-1.25-1.646-1.25-1.646-1.022-.699.078-.685.078-.685 1.13.08 1.725 1.16 1.725 1.16 1.004 1.72 2.633 1.223 3.275.935.102-.727.393-1.223.715-1.504-2.499-.284-5.126-1.25-5.126-5.565 0-1.23.44-2.233 1.16-3.02-.117-.285-.503-1.43.11-2.98 0 0 .945-.303 3.094 1.153A10.79 10.79 0 0 1 12 6.18c.956.005 1.918.13 2.818.379 2.148-1.456 3.091-1.153 3.091-1.153.615 1.55.229 2.695.112 2.98.722.787 1.158 1.79 1.158 3.02 0 4.326-2.63 5.278-5.137 5.557.404.35.764 1.04.764 2.097 0 1.514-.014 2.736-.014 3.108 0 .301.203.652.774.541A11.252 11.252 0 0 0 12 .75Z" />
          </svg>
          Войти через GitHub
        </a>
      </form>
    </div>
    <button type="button" className="link-button" onClick={() => { setRegister(!register); setError('') }}>{register ? 'Уже есть аккаунт' : 'Создать аккаунт'}</button>
    <Wordmark />
  </main>
}
