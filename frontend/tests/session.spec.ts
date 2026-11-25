import { expect, test, type Page } from '@playwright/test'

async function mockApi(page: Page) {
  await page.route('**/api/auth/login', (route) => route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer', expires_in: 1800 } }))
  await page.route('**/api/users/me', (route) => route.fulfill({ json: { id: 'test-user', email: 'test@example.com', display_name: 'Тест' } }))
  await page.route('**/api/documents?*', (route) => route.fulfill({ json: [] }))
}

async function login(page: Page) {
  await page.goto('/')
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill('test@example.com')
  await page.getByRole('textbox', { name: 'Пароль', exact: true }).fill('test-password-123')
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
}

test('session survives a page reload and ends on logout', async ({ page }) => {
  await mockApi(page)
  await login(page)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toHaveCount(0)

  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
})

test('expired token after reload returns to the login form', async ({ page }) => {
  await mockApi(page)
  await login(page)
  await page.unroute('**/api/documents?*')
  await page.route('**/api/documents?*', (route) => route.fulfill({ status: 401, json: { detail: { code: 'invalid_token', message: 'Войдите снова' } } }))
  await page.reload()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('cowrite:access-token'))).toBeNull()
})
