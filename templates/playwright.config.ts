// Config base de Playwright alinhada aos guardrails.
// Instale: npm i -D @playwright/test && npx playwright install --with-deps
import { defineConfig, devices } from '@playwright/test';

// Nunca aponte para produção. Sem env, cai no ambiente local.
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

if (/prod|\.com\b/.test(baseURL) && !process.env.E2E_ALLOW_PROD) {
  throw new Error(`E2E apontando para ambiente não-local (${baseURL}). ` +
    `Defina E2E_ALLOW_PROD=1 se isso for realmente intencional.`);
}

export default defineConfig({
  testDir: './e2e',
  // Falha o CI se alguém esquecer .only no arquivo.
  forbidOnly: !!process.env.CI,
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  reporter: process.env.CI ? [['html', { open: 'never' }], ['github']] : [['list']],

  use: {
    baseURL,
    // Diagnóstico só quando falha: rápido no caminho feliz, completo no erro.
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    // testid como seletor canônico — sobrevive a refactor de estilo.
    testIdAttribute: 'data-testid',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],

  // Sobe a aplicação sozinho; reaproveita se já estiver rodando localmente.
  webServer: {
    command: process.env.E2E_SERVER_CMD ?? 'npm run dev',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
