import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthApi } from '../core/auth-api';
import { mensagemDoErro } from '../core/erro';
import { Session } from '../core/session';

type Estado = 'pedindo' | 'enviado' | 'entrando' | 'erro';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly api = inject(AuthApi);
  private readonly session = inject(Session);
  private readonly router = inject(Router);
  private readonly rota = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('pedindo');
  protected readonly erro = signal<string | null>(null);
  protected email = '';

  constructor() {
    const token = this.rota.snapshot.queryParamMap.get('token');
    if (token) {
      this.entrarCom(token);
    }
  }

  protected pedirLink(): void {
    if (!this.email.includes('@')) {
      this.erro.set('Confira o e-mail.');
      return;
    }
    this.erro.set(null);
    this.api.pedirLink(this.email.trim()).subscribe({
      next: () => this.estado.set('enviado'),
      error: (falha: HttpErrorResponse) =>
        this.erro.set(
          falha.status === 422
            ? 'Confira o e-mail.'
            : mensagemDoErro(falha, 'Não consegui enviar o link agora. Tente de novo.'),
        ),
    });
  }

  private entrarCom(token: string): void {
    this.estado.set('entrando');
    this.api.entrar(token).subscribe({
      next: (sessao) => {
        this.session.abrir(sessao.token);
        void this.router.navigate([sessao.needs_onboarding ? '/comecar' : '/hoje']);
      },
      error: (falha: HttpErrorResponse) => {
        this.estado.set('erro');
        this.erro.set(
          falha.status === 401
            ? 'Esse link não vale mais. Peça outro — eles duram 20 minutos.'
            : mensagemDoErro(falha, 'Não consegui entrar agora. Tente o link de novo.'),
        );
      },
    });
  }
}
