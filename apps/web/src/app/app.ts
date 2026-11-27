import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { Session } from './core/session';

/** Telas sem o menu do aluno: o painel do operador e o onboarding, antes de haver plano. */
const SEM_MENU = ['/admin', '/comecar'];

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly session = inject(Session);
  private readonly router = inject(Router);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  protected readonly mostraMenu = computed(
    () =>
      this.session.autenticado() && !SEM_MENU.some((rota) => (this.url() ?? '').startsWith(rota)),
  );

  /** A grade da semana usa a largura do desktop; o resto fica na coluna de leitura. */
  protected readonly larga = computed(() => (this.url() ?? '').startsWith('/rotina'));
}
