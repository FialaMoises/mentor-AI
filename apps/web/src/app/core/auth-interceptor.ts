import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { Session } from './session';

/**
 * Rotas de entrada: um 401 aqui é "link inválido", não "sessão morreu". Quem já
 * está logado e abre um e-mail antigo continua logado.
 */
const ROTAS_DE_ENTRADA = ['/auth/verify', '/auth/magic-link'];

/** Põe o token em toda chamada e manda para o login quando a sessão morre. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(Session);
  const router = inject(Router);
  const token = session.token;

  const comToken = token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(comToken).pipe(
    catchError((erro: HttpErrorResponse) => {
      const entrada = ROTAS_DE_ENTRADA.some((rota) => req.url.includes(rota));
      if (erro.status === 401 && !entrada) {
        // Com ou sem token: sem sessão válida, a rota de aluno não tem o que mostrar.
        void session.expirar();
        void router.navigate(['/entrar']);
      }
      return throwError(() => erro);
    }),
  );
};
