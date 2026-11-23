import { expect, test } from '@playwright/test'

test('successful registration stays in login mode when automatic login is rate limited', async ({ page }) => {
  let registrations = 0
  let logins = 0
  await page.route('**/api/auth/register', (route) => {
    registrations++
    return route.fulfill({ status: 201, json: { id: 'test-user', email: 'test@example.com', display_name: 'Тест' } })
  })
  await page.route('**/api/auth/login', (route) => {
    logins++
    return logins === 1
      ? route.fulfill({ status: 429, headers: { 'Retry-After': '1' }, json: { detail: { code: 'rate_limited', message: 'Слишком много запросов' } } })
      : route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer', expires_in: 1800 } })
  })
  await page.route('**/api/documents?*', (route) => route.fulfill({ json: [] }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
  await page.getByRole('textbox', { name: 'Имя', exact: true }).fill('Тест')
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill('test@example.com')
  await page.getByRole('textbox', { name: 'Пароль', exact: true }).fill('test-password-123')
  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Слишком много запросов')
  await expect(page.getByRole('textbox', { name: 'Имя', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
  expect(registrations).toBe(1)
  expect(logins).toBe(2)
})
