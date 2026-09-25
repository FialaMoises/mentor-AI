import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AssinaturaOut, AuthApi } from '../core/auth-api';
import { Session } from '../core/session';

@Component({
  selector: 'app-subscription',
  imports: [FormsModule],
  templateUrl: './subscription.html',
  styleUrl: './subscription.scss',
})
export class SubscriptionPage {
  private readonly api = inject(AuthApi);
  private readonly session = inject(Session);
  private readonly router = inject(Router);

  protected readonly assinatura = signal<AssinaturaOut | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected readonly ocupado = signal(false);
  protected readonly confirmandoCancelamento = signal(false);
  protected pausarAte = '';

  protected readonly preco = computed(() => {
    const centavos = this.assinatura()?.price_cents ?? 0;
    return (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  });

  constructor() {
    this.carregar();
  }

  protected carregar(): void {
    this.api.assinatura().subscribe({
      next: (dados) => this.assinatura.set(dados),
      error: () => this.erro.set('Não consegui carregar sua assinatura.'),
    });
  }

  protected assinar(plano: 'mensal' | 'anual'): void {
    this.ocupado.set(true);
    this.api.pagar(plano).subscribe({
      next: (checkout) => {
        this.ocupado.set(false);
        window.location.href = checkout.url;
      },
      error: () => {
        this.ocupado.set(false);
        this.erro.set('Não consegui abrir o pagamento.');
      },
    });
  }

  protected pausar(): void {
    if (!this.pausarAte) {
      this.erro.set('Escolha até quando quer pausar.');
      return;
    }
    this.ocupado.set(true);
    this.api.pausar(this.pausarAte).subscribe({
      next: (dados) => {
        this.assinatura.set(dados);
        this.ocupado.set(false);
      },
      error: () => {
        this.ocupado.set(false);
        this.erro.set('A pausa precisa terminar no futuro.');
      },
    });
  }

  protected retomar(): void {
    this.api.retomar().subscribe({
      next: (dados) => this.assinatura.set(dados),
      error: () => this.erro.set('Não consegui retomar.'),
    });
  }

  protected cancelar(): void {
    this.api.cancelar().subscribe({
      next: (dados) => {
        this.assinatura.set(dados);
        this.confirmandoCancelamento.set(false);
      },
      error: () => this.erro.set('Não consegui cancelar.'),
    });
  }

  protected exportar(): void {
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
      error: () => this.erro.set('Não consegui montar a exportação.'),
    });
  }

  protected apagarConta(): void {
    this.api.apagarConta().subscribe({
      next: () => {
        this.session.fechar();
        void this.router.navigate(['/entrar']);
      },
      error: () => this.erro.set('Não consegui apagar a conta.'),
    });
  }

  protected sair(): void {
    this.api.sair().subscribe({
      next: () => {
        this.session.fechar();
        void this.router.navigate(['/entrar']);
      },
      error: () => {
        this.session.fechar();
        void this.router.navigate(['/entrar']);
      },
    });
  }
}
