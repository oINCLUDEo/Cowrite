import { expect, test } from '@playwright/test'

for (const mode of ['login', 'register']) {
  test(`GitHub sign-in is a keyboard-accessible button link in ${mode} mode`, async ({ page }) => {
    await page.route('**/api/auth/github/login', (route) => route.fulfill({ contentType: 'text/html', body: '<main>OAuth redirect</main>' }))
    await page.goto('/')
    if (mode === 'register') await page.getByRole('button', { name: 'Создать аккаунт' }).click()
    const github = page.getByRole('link', { name: 'Войти через GitHub', exact: true })
    await expect(github).toBeVisible()
    await expect(github).toHaveAttribute('href', '/api/auth/github/login')
    await expect(github).toHaveCSS('text-decoration-line', 'none')
    await expect(github.locator('svg')).toHaveAttribute('aria-hidden', 'true')
    await github.focus()
    await expect(github).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/api\/auth\/github\/login$/)
    await expect(page.getByRole('main')).toHaveText('OAuth redirect')
  })
}

test('OAuth callback exchanges the code and keeps the token only for this tab', async ({ page }) => {
  await page.route('**/api/auth/exchange', async (route) => {
    expect(route.request().postDataJSON()).toEqual({ code: 'test-exchange-code' })
    await route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer', expires_in: 1800 } })
  })
  await page.route('**/api/users/me', (route) => route.fulfill({ json: { id: 'test-user', email: 'test@example.com', display_name: 'Тест' } }))
  await page.route('**/api/documents?*', (route) => route.fulfill({ json: [] }))
  await page.goto('/auth/callback#code=test-exchange-code')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
  // Токен переживает F5 в этой вкладке (sessionStorage), но не пишется в localStorage, общий для всех вкладок.
  expect(await page.evaluate(() => ({ local: localStorage.length, token: sessionStorage.getItem('cowrite:access-token') })))
    .toEqual({ local: 0, token: 'test-token' })
})

test('OAuth callback shows a short error without leaking the code', async ({ page }) => {
  await page.route('**/api/auth/exchange', (route) => route.fulfill({ status: 400, json: { detail: 'Expired code' } }))
  await page.goto('/auth/callback#code=expired')
  await expect(page.getByRole('alert')).toHaveText('Не удалось войти')
  await expect(page).toHaveURL(/\/auth\/callback$/)
  await expect(page.getByRole('link', { name: 'Повторить' })).toHaveAttribute('href', '/api/auth/github/login')
})
