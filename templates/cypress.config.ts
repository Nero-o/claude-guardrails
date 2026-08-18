// Config base de Cypress alinhada aos guardrails.
// Instale: npm i -D cypress
import { defineConfig } from 'cypress';

const baseUrl = process.env.E2E_BASE_URL ?? 'http://localhost:3000';

if (/prod|\.com\b/.test(baseUrl) && !process.env.E2E_ALLOW_PROD) {
  throw new Error(`E2E apontando para ambiente não-local (${baseUrl}).`);
}

export default defineConfig({
  e2e: {
    baseUrl,
    specPattern: 'cypress/e2e/**/*.cy.{ts,tsx,js}',
    supportFile: 'cypress/support/e2e.ts',
    // Cada teste monta seu próprio estado; nada persiste entre specs.
    testIsolation: true,
    retries: { runMode: 2, openMode: 0 },
    defaultCommandTimeout: 8_000,
    requestTimeout: 10_000,
    video: false,
    screenshotOnRunFailure: true,
    viewportWidth: 1280,
    viewportHeight: 800,
    env: {
      // Credencial SEMPRE do ambiente. Nunca literal aqui.
      user: process.env.E2E_USER,
      password: process.env.E2E_PASSWORD,
    },
  },
  component: {
    devServer: { framework: 'react', bundler: 'vite' },
  },
});
