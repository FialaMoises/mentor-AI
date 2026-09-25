import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { Session } from './session';

/** Põe o token em toda chamada e manda para o login quando a sessão morre. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(Session);
  const router = inject(Router);
  const token = session.token;

  const comToken = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(comToken).pipe(
    catchError((erro: HttpErrorResponse) => {
      if (erro.status === 401 && token) {
        session.fechar();
        void router.navigate(['/entrar']);
      }
      return throwError(() => erro);
    }),
  );
};
