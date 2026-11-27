import { TestBed } from '@angular/core/testing';

import { OfflineQueue } from './offline-queue';

describe('OfflineQueue', () => {
  let fila: OfflineQueue;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    fila = TestBed.inject(OfflineQueue);
  });

  afterEach(() => localStorage.clear());

  it('dá um id próprio e a hora a cada marcação', () => {
    const primeira = fila.enfileirar({ task_id: 't1', action: 'feita' });
    const segunda = fila.enfileirar({ task_id: 't1', action: 'feita' });

    expect(primeira.client_event_id).not.toBe(segunda.client_event_id);
    expect(Date.parse(primeira.occurred_at)).not.toBeNaN();
  });

  it('sobrevive ao recarregar a página', () => {
    fila.enfileirar({ task_id: 't1', action: 'feita' });

    const outra = new OfflineQueue();
    expect(outra.todas().length).toBe(1);
    expect(outra.pendentes()).toBe(1);
  });

  it('remove só o que foi confirmado', () => {
    const primeira = fila.enfileirar({ task_id: 't1', action: 'feita' });
    fila.enfileirar({ task_id: 't2', action: 'nao_deu' });

    fila.remover([primeira.client_event_id]);

    expect(fila.todas().map((m) => m.task_id)).toEqual(['t2']);
    expect(fila.pendentes()).toBe(1);
  });

  it('não quebra quando o storage não está disponível', () => {
    spyOn(localStorage, 'getItem').and.throwError('bloqueado');
    spyOn(localStorage, 'setItem').and.throwError('bloqueado');

    const outra = new OfflineQueue();
    const marcacao = outra.enfileirar({ task_id: 't1', action: 'feita' });

    expect(marcacao.client_event_id).toBeTruthy();
    expect(outra.todas()).toEqual([]);
  });

  it('sem crypto.randomUUID (http fora de localhost), o id ainda é um UUID v4', () => {
    const original = crypto.randomUUID;
    Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true });
    try {
      const marcacao = fila.enfileirar({ task_id: 't1', action: 'feita' });
      expect(marcacao.client_event_id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      );
    } finally {
      Object.defineProperty(crypto, 'randomUUID', { value: original, configurable: true });
    }
  });
});
