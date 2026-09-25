import { Injectable, signal } from '@angular/core';

export interface MarcacaoPendente {
  task_id: string;
  action: 'feita' | 'nao_deu';
  answered?: number | null;
  correct?: number | null;
  client_event_id: string;
  occurred_at: string;
}

const CHAVE = 'mentor-ai.fila-offline';

/**
 * A fila de marcações feitas sem sinal.
 *
 * Cada marcação nasce com um id próprio: reenviar a fila inteira é seguro,
 * porque o servidor reconhece o que já aplicou.
 */
@Injectable({ providedIn: 'root' })
export class OfflineQueue {
  readonly pendentes = signal<number>(this.ler().length);

  enfileirar(marcacao: Omit<MarcacaoPendente, 'client_event_id' | 'occurred_at'>): MarcacaoPendente {
    const completa: MarcacaoPendente = {
      ...marcacao,
      client_event_id: this.novoId(),
      occurred_at: new Date().toISOString(),
    };
    const fila = [...this.ler(), completa];
    this.gravar(fila);
    return completa;
  }

  todas(): MarcacaoPendente[] {
    return this.ler();
  }

  remover(ids: string[]): void {
    const apagar = new Set(ids);
    this.gravar(this.ler().filter((m) => !apagar.has(m.client_event_id)));
  }

  limpar(): void {
    this.gravar([]);
  }

  private novoId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  private ler(): MarcacaoPendente[] {
    try {
      const bruto = localStorage.getItem(CHAVE);
      return bruto ? (JSON.parse(bruto) as MarcacaoPendente[]) : [];
    } catch {
      return [];
    }
  }

  private gravar(fila: MarcacaoPendente[]): void {
    try {
      localStorage.setItem(CHAVE, JSON.stringify(fila));
    } catch {
      // Sem storage a fila vive só nesta aba; a marcação já foi tentada na rede.
    }
    this.pendentes.set(fila.length);
  }
}
