import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SwPush } from '@angular/service-worker';

import { mensagemDoErro } from '../core/erro';
import { PlanApi } from '../core/plan-api';

type Estado =
  | 'carregando'
  | 'desligado'
  | 'indisponivel'
  | 'precisa_instalar'
  | 'pronto'
  | 'assinado'
  | 'negado';

@Component({
  selector: 'app-notifications',
  templateUrl: './notifications.html',
  styleUrl: './notifications.scss',
})
export class Notifications {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(PlanApi);
  private readonly push = inject(SwPush);

  protected readonly estado = signal<Estado>('carregando');
  protected readonly erro = signal<string | null>(null);
  private readonly chavePublica = signal<string>('');

  /** No iPhone, o push só existe depois que o app está na tela de início. */
  protected readonly ehIos = /iPad|iPhone|iPod/.test(navigator.userAgent);
  protected readonly instalado = window.matchMedia('(display-mode: standalone)').matches;
  protected readonly mostraGuiaIos = computed(() => this.ehIos && !this.instalado);

  constructor() {
    this.api
      .pushConfig()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (config) => {
          this.chavePublica.set(config.public_key);
          if (!config.enabled) {
            // A falta é do servidor (sem chave VAPID), não do aparelho do aluno.
            this.estado.set('desligado');
            return;
          }
          if (this.ehIos && !this.instalado) {
            this.estado.set('precisa_instalar');
            return;
          }
          this.estado.set(this.push.isEnabled ? 'pronto' : 'indisponivel');
        },
        error: (falha) => {
          this.estado.set('desligado');
          this.erro.set(mensagemDoErro(falha, 'Não consegui ver se os avisos estão ligados.'));
        },
      });
  }

  protected ativar(): void {
    this.erro.set(null);
    this.push
      .requestSubscription({ serverPublicKey: this.chavePublica() })
      .then((assinatura) => {
        this.api.assinarPush(assinatura.toJSON()).subscribe({
          next: () => this.estado.set('assinado'),
          error: (falha) =>
            this.erro.set(
              mensagemDoErro(falha, 'Assinei aqui, mas o servidor recusou. Tente de novo.'),
            ),
        });
      })
      .catch(() => this.estado.set('negado'));
  }
}
