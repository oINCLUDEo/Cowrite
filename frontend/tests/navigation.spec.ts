import { expect, test } from '@playwright/test'
import { register, login, createDocument } from './helpers'

test('root has no introductory page; reload keeps the session, login without it preserves document', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  const account = await register(page)
  await createDocument(page)
  const documentUrl = page.url()
  const editor = page.getByRole('textbox', { name: 'Содержимое документа' })
  // Токен в sessionStorage вкладки: после F5 тот же документ открывается без входа.
  await page.reload()
  await expect(page).toHaveURL(documentUrl)
  await expect(editor).toBeVisible()
  // Без сохранённого токена (новая вкладка или истёкший) нужен вход, а адрес документа сохраняется.
  await page.evaluate(() => sessionStorage.clear())
  await page.reload()
  await expect(page).toHaveURL(documentUrl)
  await login(page, account)
  await expect(editor).toBeVisible()
})

test('unknown page does not silently open a different document', async ({ page }) => {
  await page.goto('/documents/invalid')
  await register(page)
  await page.evaluate(() => { history.pushState(null, '', '/documents/invalid'); dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.getByRole('heading', { name: 'Страница не найдена' })).toBeVisible()
  await page.getByRole('link', { name: 'Открыть редактор' }).click()
  await expect(page).toHaveURL(/\/$/)
  // Ссылка перезагружает страницу, сессия сохраняется: открывается список, а не другой документ.
  await expect(page.getByRole('heading', { name: 'Документы', exact: true })).toBeVisible()
})
