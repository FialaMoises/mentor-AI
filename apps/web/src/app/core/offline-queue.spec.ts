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
});
