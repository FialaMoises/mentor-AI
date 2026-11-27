import { Routes } from '@angular/router';

import { authGuard } from './core/auth-guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'hoje' },
  {
    path: 'entrar',
    title: 'Entrar · mentor-AI',
    loadComponent: () => import('./login/login').then((m) => m.Login),
  },
  {
    path: 'hoje',
    title: 'Hoje · mentor-AI',
    canActivate: [authGuard],
    loadComponent: () => import('./today/today').then((m) => m.Today),
  },
  {
    path: 'comecar',
    title: 'Montar o plano · mentor-AI',
    canActivate: [authGuard],
    loadComponent: () => import('./onboarding/onboarding').then((m) => m.Onboarding),
  },
  {
    path: 'rotina',
    title: 'Minha rotina · mentor-AI',
    canActivate: [authGuard],
    loadComponent: () => import('./routine/routine').then((m) => m.Routine),
  },
  {
    path: 'avisos',
    title: 'Avisos · mentor-AI',
    canActivate: [authGuard],
    loadComponent: () => import('./notifications/notifications').then((m) => m.Notifications),
  },
  {
    path: 'conta',
    title: 'Sua conta · mentor-AI',
    canActivate: [authGuard],
    loadComponent: () => import('./subscription/subscription').then((m) => m.SubscriptionPage),
  },
  {
    path: 'admin',
    title: 'Painel do piloto · mentor-AI',
    loadComponent: () => import('./admin/admin').then((m) => m.Admin),
  },
  { path: '**', redirectTo: 'hoje' },
];
