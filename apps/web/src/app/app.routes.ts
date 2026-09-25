import { Routes } from '@angular/router';

import { authGuard } from './core/auth-guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'hoje' },
  {
    path: 'entrar',
    loadComponent: () => import('./login/login').then((m) => m.Login),
  },
  {
    path: 'hoje',
    canActivate: [authGuard],
    loadComponent: () => import('./today/today').then((m) => m.Today),
  },
  {
    path: 'comecar',
    canActivate: [authGuard],
    loadComponent: () => import('./onboarding/onboarding').then((m) => m.Onboarding),
  },
  {
    path: 'avisos',
    canActivate: [authGuard],
    loadComponent: () => import('./notifications/notifications').then((m) => m.Notifications),
  },
  {
    path: 'conta',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./subscription/subscription').then((m) => m.SubscriptionPage),
  },
  {
    path: 'admin',
    loadComponent: () => import('./admin/admin').then((m) => m.Admin),
  },
  { path: '**', redirectTo: 'hoje' },
];
