import { Injectable, signal } from '@angular/core';

const CHAVE_TOKEN = 'mentor-ai.token';
const CHAVE_ALUNO = 'mentor-ai.student-id';

/**
 * A sessão do aluno neste navegador.
 *
 * O token vem do link mágico e vale 30 dias. Guardar em `localStorage` é o que
 * permite abrir o app offline já autenticado.
 */
@Injectable({ providedIn: 'root' })
export class Session {
  readonly autenticado = signal<boolean>(this.ler(CHAVE_TOKEN) !== null);

  get token(): string | null {
    return this.ler(CHAVE_TOKEN);
  }

  get studentId(): string | null {
    return this.ler(CHAVE_ALUNO);
  }

  abrir(token: string, studentId: string): void {
    this.gravar(CHAVE_TOKEN, token);
    this.gravar(CHAVE_ALUNO, studentId);
    this.autenticado.set(true);
  }

  fechar(): void {
    this.apagar(CHAVE_TOKEN);
    this.apagar(CHAVE_ALUNO);
    this.autenticado.set(false);
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
