import { Injectable } from '@angular/core';

import { SEED_STUDENT_ID } from './config';

const CHAVE = 'mentor-ai.student-id';

/**
 * Guarda qual aluno está usando o app neste navegador.
 * A fase 5 troca isto por sessão autenticada de verdade.
 */
@Injectable({ providedIn: 'root' })
export class Session {
  get studentId(): string {
    try {
      return localStorage.getItem(CHAVE) ?? SEED_STUDENT_ID;
    } catch {
      return SEED_STUDENT_ID;
    }
  }

  set studentId(id: string) {
    try {
      localStorage.setItem(CHAVE, id);
    } catch {
      // Navegador sem storage (janela anônima): a sessão dura só esta aba.
    }
  }

  get isSeed(): boolean {
    return this.studentId === SEED_STUDENT_ID;
  }
}
