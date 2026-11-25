// Токен живёт только в памяти вкладки. Перезагрузка требует нового входа.
let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

// Выход: токен стирается, App по событию показывает форму входа.
export function logout(): void {
  setAccessToken(null)
  window.dispatchEvent(new Event('cowrite:logout'))
}
