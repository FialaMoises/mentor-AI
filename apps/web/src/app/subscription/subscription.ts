import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AssinaturaOut, AuthApi } from '../core/auth-api';
import { amanhaIso, dataCurta } from '../core/datas';
import { mensagemDoErro } from '../core/erro';
import { OfflineQueue } from '../core/offline-queue';
import { PlanApi } from '../core/plan-api';
import { rotuloStatusAssinatura } from '../core/rotulos';
import { Session } from '../core/session';

@Component({
  selector: 'app-subscription',
  imports: [FormsModule],
  templateUrl: './subscription.html',
  styleUrl: './subscription.scss',
})
export class SubscriptionPage {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(AuthApi);
  private readonly plano = inject(PlanApi);
  private readonly session = inject(Session);
  private readonly fila = inject(OfflineQueue);
  private readonly router = inject(Router);

  protected readonly dataCurta = dataCurta;
  protected readonly amanha = amanhaIso();
  protected readonly assinatura = signal<AssinaturaOut | null>(null);
  protected readonly carregando = signal(true);
  protected readonly erro = signal<string | null>(null);
  protected readonly ocupado = signal(false);
  protected readonly confirmandoCancelamento = signal(false);
  protected readonly confirmandoExclusao = signal(false);
  /** Marcações que não subiram: sair agora as apaga deste aparelho. */
  protected readonly pendentesAoSair = signal(0);
  protected pausarAte = '';

  protected readonly preco = computed(() => this.reais(this.assinatura()?.price_cents ?? 0));

  /** Marcações que subiram ao sair, mas o servidor não aceitou: a tela avisa antes. */
  protected readonly perdidasAoSair = signal(0);

  protected reais(centavos: number): string {
    return (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  protected readonly rotuloStatus = computed(() =>
    rotuloStatusAssinatura(this.assinatura()?.status ?? ''),
  );

  constructor() {
    this.carregar();
  }

  protected carregar(): void {
    this.carregando.set(true);
    this.api
      .assinatura()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (dados) => {
          this.assinatura.set(dados);
          this.carregando.set(false);
        },
        error: (falha) => {
          this.carregando.set(false);
          this.erro.set(mensagemDoErro(falha, 'Não consegui carregar sua assinatura.'));
        },
      });
  }

  /** Só segue para o pagamento por https: uma resposta adulterada não leva a `javascript:`. */
  protected urlDeCheckoutSegura(url: string): boolean {
    try {
      return new URL(url).protocol === 'https:';
    } catch {
      return false;
    }
  }

  protected assinar(plano: 'mensal' | 'anual'): void {
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.api.pagar(plano).subscribe({
      next: (checkout) => {
        this.ocupado.set(false);
        if (!this.urlDeCheckoutSegura(checkout.url)) {
          this.erro.set('O endereço do pagamento não parece seguro. Tente de novo mais tarde.');
          return;
        }
        window.location.href = checkout.url;
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui abrir o pagamento.'));
      },
    });
  }

  protected pausar(): void {
    if (!this.pausarAte) {
      this.erro.set('Escolha até quando quer pausar.');
      return;
    }
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.api.pausar(this.pausarAte).subscribe({
      next: (dados) => {
        this.assinatura.set(dados);
        this.ocupado.set(false);
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui pausar. Tente de novo.'));
      },
    });
  }

  protected retomar(): void {
    this.erro.set(null);
    this.api.retomar().subscribe({
      next: (dados) => this.assinatura.set(dados),
      error: (falha) => this.erro.set(mensagemDoErro(falha, 'Não consegui retomar.')),
    });
  }

  protected cancelar(): void {
    this.erro.set(null);
    this.api.cancelar().subscribe({
      next: (dados) => {
        this.assinatura.set(dados);
        this.confirmandoCancelamento.set(false);
      },
      error: (falha) => this.erro.set(mensagemDoErro(falha, 'Não consegui cancelar.')),
    });
  }

  protected exportar(): void {
    this.erro.set(null);
    this.api.exportarDados().subscribe({
      next: (dados) => {
        const arquivo = new Blob([JSON.stringify(dados, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(arquivo);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'meus-dados-mentor-ai.json';
        link.click();
        URL.revokeObjectURL(url);
      },
      error: (falha) => this.erro.set(mensagemDoErro(falha, 'Não consegui montar a exportação.')),
    });
  }

  /** A exclusão não tem volta: o primeiro toque só abre a confirmação. */
  protected pedirExclusao(): void {
    this.confirmandoCancelamento.set(false);
    this.confirmandoExclusao.set(true);
  }

  protected apagarConta(): void {
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.api.apagarConta().subscribe({
      next: () => {
        this.ocupado.set(false);
        void this.session.fechar();
        void this.router.navigate(['/entrar']);
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui apagar a conta.'));
      },
    });
  }

  /**
   * Antes de sair, tenta subir as marcações feitas sem internet. Se não der,
   * avisa quantas se perdem e só sai com a confirmação do aluno.
   */
  protected sair(): void {
    const fila = this.fila.todas();
    if (!fila.length) {
      this.encerrar();
      return;
    }
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.plano.sync(fila).subscribe({
      next: (resultado) => {
        this.ocupado.set(false);
        this.fila.remover(fila.map((m) => m.client_event_id));
        const perdidas =
          (resultado.unknown ?? 0) + (resultado.rejected ?? 0) + (resultado.stale ?? 0);
        if (perdidas > 0) {
          // Como no /hoje: a marcação recusada não some em silêncio.
          this.perdidasAoSair.set(perdidas);
          return;
        }
        this.encerrar();
      },
      error: () => {
        this.ocupado.set(false);
        this.pendentesAoSair.set(fila.length);
      },
    });
  }

  protected encerrar(): void {
    this.pendentesAoSair.set(0);
    this.perdidasAoSair.set(0);
    const fim = () => {
      void this.session.fechar();
      void this.router.navigate(['/entrar']);
    };
    this.api.sair().subscribe({ next: fim, error: fim });
  }
}
