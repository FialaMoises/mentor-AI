import { Component, computed, inject, signal } from '@angular/core';
import { SwPush } from '@angular/service-worker';

import { PlanApi } from '../core/plan-api';
import { Session } from '../core/session';

type Estado = 'carregando' | 'indisponivel' | 'precisa_instalar' | 'pronto' | 'assinado' | 'negado';

@Component({
  selector: 'app-notifications',
  templateUrl: './notifications.html',
  styleUrl: './notifications.scss',
})
export class Notifications {
  private readonly api = inject(PlanApi);
  private readonly session = inject(Session);
  private readonly push = inject(SwPush);

  protected readonly estado = signal<Estado>('carregando');
  protected readonly erro = signal<string | null>(null);
  private readonly chavePublica = signal<string>('');

  /** No iPhone, o push só existe depois que o app está na tela de início. */
  protected readonly ehIos = /iPad|iPhone|iPod/.test(navigator.userAgent);
  protected readonly instalado = window.matchMedia('(display-mode: standalone)').matches;
  protected readonly mostraGuiaIos = computed(
    () => this.ehIos && !this.instalado,
  );

  constructor() {
    this.api.pushConfig().subscribe({
      next: (config) => {
        this.chavePublica.set(config.public_key);
        if (!config.enabled) {
          this.estado.set('indisponivel');
          return;
        }
        if (this.ehIos && !this.instalado) {
          this.estado.set('precisa_instalar');
          return;
        }
        this.estado.set(this.push.isEnabled ? 'pronto' : 'indisponivel');
      },
      error: () => this.estado.set('indisponivel'),
    });
  }

  protected ativar(): void {
    this.erro.set(null);
    this.push
      .requestSubscription({ serverPublicKey: this.chavePublica() })
      .then((assinatura) => {
        this.api.assinarPush(this.session.studentId, assinatura.toJSON()).subscribe({
          next: () => this.estado.set('assinado'),
          error: () => this.erro.set('Assinei aqui, mas o servidor recusou. Tente de novo.'),
        });
      })
      .catch(() => this.estado.set('negado'));
  }
}
