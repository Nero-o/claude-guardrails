// Teste unitário exemplar (Jest ou Vitest — a API usada aqui é comum aos dois).
// Prova: regra de negócio isolada, determinística, uma asserção por comportamento.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { calcularJuros } from '../src/financeiro';

describe('calcularJuros', () => {
  beforeEach(() => {
    // Tempo congelado: teste que depende do relógio real falha sozinho um dia.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-15T12:00:00Z'));
  });
  afterEach(() => vi.useRealTimers());

  // Nome descreve o COMPORTAMENTO, não o método.
  it('aplica a taxa proporcional aos dias corridos', () => {
    expect(calcularJuros({ principal: 1000, taxaAnual: 0.12, dias: 30 })).toBeCloseTo(9.86, 2);
  });

  it('retorna zero quando o prazo é zero', () => {
    expect(calcularJuros({ principal: 1000, taxaAnual: 0.12, dias: 0 })).toBe(0);
  });

  // Caminho de erro é comportamento: teste como qualquer outro.
  it('rejeita principal negativo', () => {
    expect(() => calcularJuros({ principal: -1, taxaAnual: 0.12, dias: 30 }))
      .toThrow(/principal/i);
  });
});
