import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'
import { createDocument, register } from '../tests/helpers'

function compose(...args: string[]) {
  return execFileSync('docker', ['compose', ...args], {
    cwd: fileURLToPath(new URL('../..', import.meta.url)),
    timeout: 60000,
    stdio: 'pipe',
  })
}

test('Mailpit, queued export, worker redelivery and API persistence', async ({ browser, request }) => {
  const owner = await browser.newContext()
  const member = await browser.newContext()
  const page = await owner.newPage()
  const recipient = await member.newPage()
  let workerStopped = false
  try {
    await register(page)
    const invited = await register(recipient)
    const path = await createDocument(page)
    const editor = page.getByRole('textbox', { name: 'Содержимое документа' })
    await editor.fill('Подтверждённое состояние после перезапуска')
    await expect(page.getByRole('status')).toHaveText('Сохранено')
    await page.getByRole('button', { name: 'Поделиться', exact: true }).click()
    await page.getByRole('textbox', { name: 'Email участника' }).fill(invited.email)
    await page.getByRole('button', { name: 'Предоставить доступ' }).click()
    await expect(page.getByText(invited.email, { exact: true })).toBeVisible()
    await expect.poll(async () => {
      const response = await request.get(`${process.env.MAILPIT_URL ?? 'http://127.0.0.1:8025'}/api/v1/messages`)
      expect(response.ok()).toBeTruthy()
      const result = await response.json() as { messages: { To: { Address: string }[] }[] }
      return result.messages.some((message) => message.To.some((to) => to.Address === invited.email))
    }, { timeout: 30000, intervals: [1000] }).toBe(true)

    compose('stop', 'worker')
    workerStopped = true
    const accepted = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/export'))
    await page.getByRole('button', { name: 'PDF', exact: true }).click()
    const response = await accepted
    expect(response.status()).toBe(202)
    const { task_id: jobId } = await response.json() as { task_id: string }
    const authorization = response.request().headers().authorization
    const jobUrl = `/api/exports/${jobId}`
    const queued = await request.get(jobUrl, { headers: { authorization } })
    expect((await queued.json()).status).toBe('queued')
    // Пока воркер стоит, задание в очереди; после запуска интерфейс сам скачает готовый файл.
    const download = page.waitForEvent('download', { timeout: 45000 })
    compose('start', 'worker')
    workerStopped = false
    expect((await download).suggestedFilename()).toMatch(/\.pdf$/)
    const original = await request.get(`${jobUrl}/file`, { headers: { authorization } })
    expect(original.headers()['content-type']).toContain('application/pdf')
    const bytes = await original.body()
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-')
    // Повторная доставка должна завершиться, не меняя уже готовый файл.
    const duplicateId = compose('exec', '-T', 'worker', 'celery', '-A', 'app.worker:celery', 'call', 'cowrite.pdf', '--args', JSON.stringify([jobId])).toString().trim()
    await expect.poll(() => compose('exec', '-T', 'worker', 'python', '-c', 'import sys; from app.worker import celery; print(celery.AsyncResult(sys.argv[1]).state)', duplicateId).toString().trim(), { timeout: 30000 }).toBe('SUCCESS')
    const repeated = await request.get(`${jobUrl}/file`, { headers: { authorization } })
    expect(await repeated.body()).toEqual(bytes)

    compose('restart', 'api')
    await expect.poll(async () => {
      const ready = await request.get('/api/health/ready')
      return ready.status()
    }, { timeout: 45000 }).toBe(200)
    // Токен живёт в sessionStorage вкладки, поэтому после F5 входить заново не нужно.
    await page.reload()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await expect(editor).toHaveText('Подтверждённое состояние после перезапуска')
  } finally {
    if (workerStopped) compose('start', 'worker')
    await owner.close()
    await member.close()
  }
})
