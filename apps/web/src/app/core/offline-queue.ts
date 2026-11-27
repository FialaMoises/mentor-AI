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

  enfileirar(
    marcacao: Omit<MarcacaoPendente, 'client_event_id' | 'occurred_at'>,
  ): MarcacaoPendente {
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
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    // `randomUUID` só existe em contexto seguro (https ou localhost); fora dele,
    // monta o UUID v4 à mão. A API exige `format: uuid` no client_event_id.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
