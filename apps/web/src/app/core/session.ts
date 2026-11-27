import { Injectable, inject, signal } from '@angular/core';

import { OfflineQueue } from './offline-queue';

const CHAVE_TOKEN = 'mentor-ai.token';
/** Chave da fase 0, que nada lê: sai do aparelho no próximo `abrir`/`fechar`. */
const CHAVE_ALUNO_ANTIGA = 'mentor-ai.student-id';

/**
 * A sessão do aluno neste navegador.
 *
 * O token vem do link mágico e vale 30 dias. Guardar em `localStorage` é o que
 * permite abrir o app offline já autenticado.
 */
@Injectable({ providedIn: 'root' })
export class Session {
  private readonly fila = inject(OfflineQueue);

  readonly autenticado = signal<boolean>(this.ler(CHAVE_TOKEN) !== null);

  /** Lê o storage de verdade: se o token sumiu, o menu acompanha. */
  get token(): string | null {
    const token = this.ler(CHAVE_TOKEN);
    if ((token !== null) !== this.autenticado()) {
      this.autenticado.set(token !== null);
    }
    return token;
  }

  abrir(token: string): void {
    this.gravar(CHAVE_TOKEN, token);
    this.apagar(CHAVE_ALUNO_ANTIGA);
    this.autenticado.set(true);
  }

  /**
   * Sair, apagar a conta ou perder a sessão (401): nada do aluno fica no aparelho.
   * A fila offline e o cache de dados do service worker (a lista do dia, guardada
   * pela URL e sem olhar o token) vão junto, para o próximo aluno não ver nada.
   */
  fechar(): Promise<void> {
    this.apagar(CHAVE_TOKEN);
    this.apagar(CHAVE_ALUNO_ANTIGA);
    this.fila.limpar();
    this.autenticado.set(false);
    return this.limparCacheDeDados();
  }

  /**
   * A sessão caiu (401): o token e o cache de dados saem, mas a fila offline fica.
   * O aluno entra de novo e as marcações sobem; se quem entrar for outro aluno, o
   * servidor responde `unknown` e o /hoje avisa. Sair e apagar a conta usam `fechar()`.
   */
  expirar(): Promise<void> {
    this.apagar(CHAVE_TOKEN);
    this.apagar(CHAVE_ALUNO_ANTIGA);
    this.autenticado.set(false);
    return this.limparCacheDeDados();
  }

  private async limparCacheDeDados(): Promise<void> {
    try {
      if (typeof caches === 'undefined') return;
      const nomes = await caches.keys();
      await Promise.all(
        nomes
          .filter((nome) => nome.startsWith('ngsw:') && nome.includes(':data:'))
          .map((nome) => caches.delete(nome)),
      );
    } catch {
      // Sem Cache Storage (janela anônima, navegador antigo): não há o que limpar.
    }
  }

  private ler(chave: string): string | null {
    try {
      return localStorage.getItem(chave);
    } catch {
      return null;
    }
  }

  private gravar(chave: string, valor: string): void {
    try {
      localStorage.setItem(chave, valor);
    } catch {
      // Janela anônima: a sessão dura só esta aba.
    }
  }

  private apagar(chave: string): void {
    try {
      localStorage.removeItem(chave);
    } catch {
      // Nada a fazer.
    }
  }
}
