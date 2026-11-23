import { randomUUID } from 'node:crypto'
import { expect, type Page } from '@playwright/test'

async function submitAuth(page: Page, path: string, label: string) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const received = page.waitForResponse((response) => response.url().endsWith(path) && response.request().method() === 'POST')
    await page.getByRole('button', { name: label, exact: true }).click()
    const response = await received
    if (response.status() !== 429) {
      expect(response.ok()).toBeTruthy()
      return
    }
    // Все браузеры локального стенда имеют один IP. Соблюдаем реальный лимит,
    // не отключаем защиту и не подменяем forwarded-заголовки ради тестов.
    const seconds = Number(response.headers()['retry-after'])
    expect(seconds).toBeGreaterThan(0)
    expect(seconds).toBeLessThanOrEqual(60)
    await page.waitForTimeout((seconds + 1) * 1000)
  }
  throw new Error('Auth rate limit did not recover after Retry-After')
}

export async function register(page: Page) {
  const email = `${randomUUID()}@example.com`
  const password = 'browser-test-password-123'
  await page.goto('/')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()
  await page.getByRole('textbox', { name: 'Имя', exact: true }).fill('Участник')
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill(email)
  await page.getByRole('textbox', { name: 'Пароль', exact: true }).fill(password)
  const loggedIn = page.waitForResponse((response) => response.url().endsWith('/auth/login') && response.request().method() === 'POST', { timeout: 120000 })
  await submitAuth(page, '/auth/register', 'Зарегистрироваться')
  const result = await loggedIn
  if (result.status() === 429) {
    await page.waitForTimeout((Number(result.headers()['retry-after']) + 1) * 1000)
    await submitAuth(page, '/auth/login', 'Войти')
  } else expect(result.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
  return { email, password }
}

export async function login(page: Page, account: { email: string; password: string }) {
  await page.getByRole('textbox', { name: 'Email', exact: true }).fill(account.email)
  await page.getByRole('textbox', { name: 'Пароль', exact: true }).fill(account.password)
  await submitAuth(page, '/auth/login', 'Войти')
}

export async function createDocument(page: Page) {
  await page.getByRole('button', { name: 'Новый документ', exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'Содержимое документа' })).toBeVisible()
  return new URL(page.url()).pathname
}
