// E2E exemplar em Cypress — mesmas regras, sintaxe da ferramenta.
describe('login', () => {
  beforeEach(() => {
    // Estado montado pelo próprio teste: nada herdado do spec anterior.
    cy.intercept('POST', '**/api/auth/login').as('login');
    cy.visit('/login');
  });

  it('usuário autenticado chega ao painel', () => {
    cy.get('[data-testid=email]').type(Cypress.env('user'));
    cy.get('[data-testid=senha]').type(Cypress.env('password'), { log: false });
    cy.contains('button', /entrar/i).click();

    // Espera pela REQUISIÇÃO, não por tempo fixo.
    cy.wait('@login').its('response.statusCode').should('eq', 200);
    cy.get('[data-testid=painel-saldo]').should('be.visible');
    cy.location('pathname').should('match', /\/painel/);
  });

  it('credencial inválida mostra erro', () => {
    cy.get('[data-testid=email]').type(Cypress.env('user'));
    cy.get('[data-testid=senha]').type('senha-errada', { log: false });
    cy.contains('button', /entrar/i).click();

    cy.wait('@login').its('response.statusCode').should('eq', 401);
    cy.get('[role=alert]').should('contain.text', 'inválid');
  });
});
