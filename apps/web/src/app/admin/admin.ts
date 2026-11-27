import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import { AdminApi, Metricas } from '../core/admin-api';
import { mensagemDoErro } from '../core/erro';
import { rotuloStatusAssinatura } from '../core/rotulos';

/**
 * O painel do piloto. O token fica só nesta aba: não é para deixar salvo num
 * navegador que não seja o seu.
 */
@Component({
  selector: 'app-admin',
  imports: [FormsModule, DecimalPipe],
  templateUrl: './admin.html',
  styleUrl: './admin.scss',
})
export class Admin {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(AdminApi);

  protected readonly metricas = signal<Metricas | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected token = '';

  protected carregar(): void {
    this.erro.set(null);
    this.api
      .metricas(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (dados) => this.metricas.set(dados),
        error: (falha: HttpErrorResponse) =>
          this.erro.set(
            falha.status === 403
              ? 'Token recusado.'
              : mensagemDoErro(falha, 'Não consegui carregar os números.'),
          ),
      });
  }

  protected porcentagem(valor: number): string {
    return `${Math.round(valor * 100)}%`;
  }

  protected statusList(mapa: Record<string, number>): { nome: string; total: number }[] {
    return Object.entries(mapa).map(([nome, total]) => ({
      nome: rotuloStatusAssinatura(nome),
      total,
    }));
  }
}
