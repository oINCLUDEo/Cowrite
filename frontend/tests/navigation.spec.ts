import { expect, test } from '@playwright/test'
import { register, login, createDocument } from './helpers'

test('root has no introductory page; reload requires login and preserves document', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  const account = await register(page)
  await createDocument(page)
  const documentUrl = page.url()
  await page.reload()
  await expect(page).toHaveURL(documentUrl)
  await login(page, account)
  await expect(page.getByRole('textbox', { name: 'Содержимое документа' })).toBeVisible()
})

test('unknown page does not silently open a different document', async ({ page }) => {
  await page.goto('/documents/invalid')
  await register(page)
  await page.evaluate(() => { history.pushState(null, '', '/documents/invalid'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.getByRole('heading', { name: 'Страница не найдена' })).toBeVisible()
  await page.getByRole('link', { name: 'Открыть редактор' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
})
