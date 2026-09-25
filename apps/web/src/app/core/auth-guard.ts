import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { Session } from './session';

/** Rota de aluno sem sessão vai para o login. */
export const authGuard: CanActivateFn = () => {
  const session = inject(Session);
  const router = inject(Router);

  if (session.token) {
    return true;
  }
  return router.createUrlTree(['/entrar']);
};
