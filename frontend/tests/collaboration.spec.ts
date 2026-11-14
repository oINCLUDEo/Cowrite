import { expect, test } from '@playwright/test'
import { register, createDocument } from './helpers'

test('two browsers synchronize text, formatting and presence', async ({ browser }) => {
  test.setTimeout(180000)
  const first = await browser.newContext()
  const second = await browser.newContext()
  const page1 = await first.newPage()
  const page2 = await second.newPage()
  const errors: string[] = []
  page1.on('pageerror', (error) => errors.push(error.message))
  page2.on('pageerror', (error) => errors.push(error.message))
  try {
    await register(page1)
    const account2 = await register(page2)
    const path = await createDocument(page1)
    await page1.getByRole('button', { name: 'Доступ', exact: true }).click()
    await page1.getByRole('textbox', { name: 'Email участника' }).fill(account2.email)
    await page1.getByRole('button', { name: 'Предоставить доступ' }).click()
    await expect(page1.getByText(account2.email, { exact: true })).toBeVisible()
    await page1.getByRole('button', { name: 'Доступ', exact: true }).click()
    // Переход внутри SPA сохраняет JWT в памяти вкладки.
    await page2.evaluate((url) => { history.pushState(null, '', url); dispatchEvent(new PopStateEvent('popstate')) }, path)
    const editor1 = page1.getByRole('textbox', { name: 'Содержимое документа' })
    const editor2 = page2.getByRole('textbox', { name: 'Содержимое документа' })
    const documentText = async (editor: typeof editor1) => editor.evaluate((element) => {
      const copy = element.cloneNode(true) as HTMLElement
      copy.querySelectorAll('.collaboration-carets__caret').forEach((caret) => caret.remove())
      return copy.textContent
    })
    await editor1.fill('Привет из первого окна')
    await expect.poll(() => documentText(editor2)).toBe('Привет из первого окна')
    await editor2.click()
    await page2.keyboard.press('Control+End')
    await page2.keyboard.insertText(' и из второго')
    await expect.poll(() => documentText(editor1)).toBe('Привет из первого окна и из второго')
    await expect(page1.locator('.collaboration-carets__label')).toBeVisible()
    await page2.keyboard.press('Control+a')
    await page2.getByRole('button', { name: 'Жирный' }).click()
    await expect.poll(() => documentText(editor1.locator('strong'))).toBe('Привет из первого окна и из второго')
    await expect(page1.getByRole('status')).toHaveText('Сохранено')
    await page1.getByRole('button', { name: 'История', exact: true }).click()
    await page1.getByRole('button', { name: 'Сохранить версию' }).click()
    await expect(page1.getByRole('button', { name: 'Восстановить' })).toHaveCount(1)
    await page1.getByRole('button', { name: 'PDF', exact: true }).click()
    await page1.getByRole('button', { name: 'Создать PDF' }).click()
    await expect(page1.getByRole('button', { name: 'Скачать PDF' })).toBeVisible({ timeout: 30000 })
    const download = page1.waitForEvent('download')
    await page1.getByRole('button', { name: 'Скачать PDF' }).click()
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/)
    expect(errors).toEqual([])
  } finally {
    await first.close()
    await second.close()
  }
})

test('active clients recover from restore, role changes and a network interruption', async ({ browser }) => {
  test.setTimeout(180000)
  const owner = await browser.newContext()
  const member = await browser.newContext()
  const first = await owner.newPage()
  const second = await member.newPage()
  first.on('dialog', (dialog) => { void dialog.accept() })
  second.on('dialog', (dialog) => { void dialog.accept() })
  try {
    await register(first)
    const account = await register(second)
    const path = await createDocument(first)
    await first.getByRole('button', { name: 'Доступ', exact: true }).click()
    await first.getByRole('textbox', { name: 'Email участника' }).fill(account.email)
    await first.getByRole('button', { name: 'Предоставить доступ' }).click()
    await expect(first.getByText(account.email, { exact: true })).toBeVisible()
    await second.evaluate((url) => { history.pushState(null, '', url); dispatchEvent(new PopStateEvent('popstate')) }, path)
    const editor1 = first.getByRole('textbox', { name: 'Содержимое документа' })
    const editor2 = second.getByRole('textbox', { name: 'Содержимое документа' })
    // Метки курсоров содержат имена, но не являются текстом документа.
    const text = (editor: typeof editor1) => editor.evaluate((element) => {
      const copy = element.cloneNode(true) as HTMLElement
      copy.querySelectorAll('.collaboration-carets__caret').forEach((caret) => caret.remove())
      return copy.textContent
    })
    await editor1.fill('Сохранённая версия')
    await expect.poll(() => text(editor2)).toBe('Сохранённая версия')
    await first.getByRole('button', { name: 'История', exact: true }).click()
    await first.getByRole('button', { name: 'Сохранить версию' }).click()
    await expect(first.getByRole('button', { name: 'Восстановить' })).toHaveCount(1)
    await editor2.fill('Изменённый текст')
    await expect.poll(() => text(editor1)).toBe('Изменённый текст')
    await first.getByRole('button', { name: 'Восстановить' }).click()
    await expect.poll(() => text(editor1)).toBe('Сохранённая версия')
    await expect.poll(() => text(editor2)).toBe('Сохранённая версия')

    await first.getByRole('button', { name: 'Доступ', exact: true }).click()
    await first.getByRole('textbox', { name: 'Email участника' }).fill(account.email)
    await first.getByRole('combobox', { name: 'Роль участника' }).selectOption('viewer')
    await first.getByRole('button', { name: 'Предоставить доступ' }).click()
    await expect(editor2).toHaveAttribute('contenteditable', 'false')
    await expect(second.getByRole('navigation', { name: 'Форматирование текста' })).toHaveCount(0)
    await first.getByRole('combobox', { name: 'Роль участника' }).selectOption('editor')
    await first.getByRole('button', { name: 'Предоставить доступ' }).click()
    await expect(editor2).toHaveAttribute('contenteditable', 'true')

    await member.setOffline(true)
    await expect(second.getByRole('status')).toHaveText('Нет соединения')
    await editor2.fill('Правка при обрыве сети')
    await member.setOffline(false)
    await expect.poll(() => text(editor1)).toBe('Правка при обрыве сети')
    await expect(second.getByRole('status')).toHaveText('Сохранено')
  } finally {
    await owner.close()
    await member.close()
  }
})
