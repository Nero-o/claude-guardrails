// E2E exemplar em Playwright.
// Prova: seletor estável, espera por condição, credencial do ambiente,
// estado montado pelo próprio teste.
import { test, expect } from '@playwright/test';

const USER = process.env.E2E_USER ?? 'usuario.teste@example.com';
const PASS = process.env.E2E_PASSWORD; // sem literal: falha cedo se não configurado

test.beforeAll(() => {
  if (!PASS) throw new Error('Defina E2E_PASSWORD no ambiente antes de rodar o E2E.');
});

test.describe('login', () => {
  test('usuário autenticado chega ao painel', async ({ page }) => {
    await page.goto('/login');

    // getByRole/getByTestId sobrevivem a refactor de CSS; seletor de classe não.
    await page.getByTestId('email').fill(USER);
    await page.getByTestId('senha').fill(PASS!);
    await page.getByRole('button', { name: /entrar/i }).click();

    // Espera por CONDIÇÃO — o expect faz auto-retry. Nada de waitForTimeout.
    await expect(page.getByTestId('painel-saldo')).toBeVisible();
    await expect(page).toHaveURL(/\/painel/);
  });

  test('credencial inválida mostra erro e mantém o usuário na tela', async ({ page }) => {
    await page.goto('/login');
    await page.getByTestId('email').fill(USER);
    await page.getByTestId('senha').fill('senha-errada');
    await page.getByRole('button', { name: /entrar/i }).click();

    await expect(page.getByRole('alert')).toContainText(/inválid/i);
    await expect(page).toHaveURL(/\/login/);
  });
});
