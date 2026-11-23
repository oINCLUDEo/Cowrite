import { expect, test } from '@playwright/test'
import { createDocument, register } from './helpers'

test('export can be retried after status polling fails', async ({ page }) => {
  await register(page)
  await createDocument(page)
  let jobs = 0
  await page.route('**/api/documents/*/export', (route) => route.fulfill({ status: 202, json: { task_id: `test-job-${++jobs}` } }))
  let polls = 0
  await page.route('**/api/exports/test-job-*', (route) => {
    polls++
    return polls === 1
      ? route.fulfill({ status: 503, json: { detail: { code: 'unavailable', message: 'Сервис временно недоступен' } } })
      : route.fulfill({ json: { status: 'succeeded', error_code: null } })
  })
  await page.getByRole('button', { name: 'PDF', exact: true }).click()
  await page.getByRole('button', { name: 'Создать PDF' }).click()
  await expect(page.getByRole('alert')).toHaveText('Сервис временно недоступен')
  await expect(page.getByRole('button', { name: 'Создать PDF' })).toBeEnabled()
  await page.getByRole('button', { name: 'Создать PDF' }).click()
  await expect(page.getByRole('button', { name: 'Скачать PDF' })).toBeVisible()
  expect(polls).toBe(2)
})

test('PDF download with an expired session returns to login', async ({ page }) => {
  await register(page)
  await createDocument(page)
  const documentUrl = page.url()
  await page.route('**/api/documents/*/export', (route) => route.fulfill({ status: 202, json: { task_id: 'test-job' } }))
  await page.route('**/api/exports/test-job', (route) => route.fulfill({ json: { status: 'succeeded', error_code: null } }))
  await page.route('**/api/exports/test-job/file', (route) => route.fulfill({ status: 401, json: { detail: { code: 'invalid_token', message: 'Войдите снова' } } }))
  await page.getByRole('button', { name: 'PDF', exact: true }).click()
  await page.getByRole('button', { name: 'Создать PDF' }).click()
  await page.getByRole('button', { name: 'Скачать PDF' }).click()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  await expect(page).toHaveURL(documentUrl)
})
