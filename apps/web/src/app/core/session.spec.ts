import { TestBed } from '@angular/core/testing';

import { OfflineQueue } from './offline-queue';
import { Session } from './session';

describe('Session', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
  });

  afterEach(() => localStorage.clear());

  it('fechar a sessão apaga a fila offline deste aparelho', () => {
    const fila = TestBed.inject(OfflineQueue);
    const session = TestBed.inject(Session);
    session.abrir('token');
    fila.enfileirar({ task_id: 't1', action: 'feita' });

    session.fechar();

    expect(fila.todas().length).toBe(0);
    expect(fila.pendentes()).toBe(0);
    expect(session.token).toBeNull();
    expect(session.autenticado()).toBeFalse();
  });

  it('fechar a sessão apaga o cache de dados do service worker (lista de outro aluno)', async () => {
    const apagados: string[] = [];
    spyOn(caches, 'keys').and.resolveTo([
      'ngsw:/:1:data:dynamic:plano-do-dia:cache',
      'ngsw:/:db:ngsw:/:1:data:dynamic:plano-do-dia:age',
      'ngsw:/:1:assets:app:cache',
    ]);
    spyOn(caches, 'delete').and.callFake(async (nome: string) => {
      apagados.push(nome);
      return true;
    });

    await TestBed.inject(Session).fechar();

    expect(apagados).toEqual([
      'ngsw:/:1:data:dynamic:plano-do-dia:cache',
      'ngsw:/:db:ngsw:/:1:data:dynamic:plano-do-dia:age',
    ]);
  });

  it('não guarda mais o id do aluno no aparelho', () => {
    TestBed.inject(Session).abrir('token');

    expect(localStorage.getItem('mentor-ai.student-id')).toBeNull();
  });

  it('sessão sem token no storage deixa de contar como aberta', () => {
    const session = TestBed.inject(Session);
    session.abrir('token');
    localStorage.removeItem('mentor-ai.token');

    expect(session.token).toBeNull();
    expect(session.autenticado()).toBeFalse();
  });

  it('sessão que expirou (401) apaga o token mas guarda a fila para subir depois', async () => {
    const fila = TestBed.inject(OfflineQueue);
    const session = TestBed.inject(Session);
    session.abrir('token');
    fila.enfileirar({ task_id: 't1', action: 'feita' });

    await session.expirar();

    expect(session.token).toBeNull();
    expect(session.autenticado()).toBeFalse();
    expect(fila.todas().length).toBe(1);
  });
});
