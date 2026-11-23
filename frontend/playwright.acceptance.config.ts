import { defineConfig } from '@playwright/test'

// Эти проверки перезапускают сервисы только явно выбранного Compose-проекта.
export default defineConfig({
  testDir: './acceptance',
  workers: 1,
  timeout: 180000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080',
    headless: true,
    trace: 'retain-on-failure',
  },
})
