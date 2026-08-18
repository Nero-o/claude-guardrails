[guardrails] Regras ativas neste repositorio (o plugin bloqueia automaticamente o que estiver marcado):

SEGURANCA
- Segredo nunca no codigo, nem em teste ou comentario. Leia de env; registre so o NOME em .env.example. [bloqueado]
- Nunca leia .env real: o conteudo vaza para o contexto e para o transcript. [confirmacao]
- SQL sempre parametrizado; comando de sistema sem shell=True; entrada do usuario validada na borda.
- Autenticado != autorizado: todo acesso a dado de terceiro checa permissao daquele registro.
- Erro para o cliente e generico; stack trace e query ficam no log. Log nunca registra senha, token, CPF/CNPJ.

TESTES
- Codigo de producao alterado exige teste tocado. [bloqueia o encerramento]
  Saidas validas: escrever o teste; apontar o teste existente (arquivo:linha); dizer por que nao e testavel.
- Unitario (Jest/Vitest/pytest) = logica e regra de negocio. E2E (Playwright/Cypress) = fluxo do usuario na tela.
  Regra de calculo nao se valida em E2E.
- Teste vale se falha sem a mudanca. Sem .only [bloqueado], sem espera por tempo fixo, sem depender de ordem.
- E2E: seletor data-testid ou role, espera por condicao, credencial do ambiente, nunca aponta para producao.

DESENVOLVIMENTO
- Leia antes de editar. Siga a convencao do codigo vizinho.
- Nao invente dependencia, API nem comando: confirme no repositorio.
- Escopo e contrato: refatoracao nao pedida vira outro pedido.
- Nunca commite ou push sem o usuario pedir. Nunca --no-verify [bloqueado]. Nunca force push em branch protegida [bloqueado].

CONCLUIR SIGNIFICA
  guardrails check passa | guardrails scan limpo | teste escrito | sem .only/debugger no diff |
  decisoes e exclusoes ditas ao usuario.

Guardrail errado se ajusta, nao se burla: /guardrails para ver como. Detalhe completo: skill "guardrails".
