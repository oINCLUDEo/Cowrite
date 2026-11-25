// Токен хранится в sessionStorage: переживает обновление страницы в этой вкладке и стирается при её закрытии.
// Срок жизни задаёт сервер (30 минут): просроченный токен после F5 получит 401, и apiResponse вернёт на вход.
const storageKey = 'cowrite:access-token'

// Хранилище может быть недоступно (запрет cookie и данных сайта): тогда токен живёт только в памяти, как раньше.
function readStored(): string | null {
  try { return sessionStorage.getItem(storageKey) } catch { return null }
}

let accessToken: string | null = readStored()

export function setAccessToken(token: string | null): void {
  accessToken = token
  try {
    if (token) sessionStorage.setItem(storageKey, token)
    else sessionStorage.removeItem(storageKey)
  } catch { /* без хранилища остаётся токен в памяти */ }
}

export function getAccessToken(): string | null {
  return accessToken
}

// Выход: токен стирается и из памяти, и из хранилища, App по событию показывает форму входа.
export function logout(): void {
  setAccessToken(null)
  window.dispatchEvent(new Event('cowrite:logout'))
}
