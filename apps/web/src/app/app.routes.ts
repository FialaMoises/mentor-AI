import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'hoje' },
  {
    path: 'hoje',
    loadComponent: () => import('./today/today').then((m) => m.Today),
  },
  {
    path: 'comecar',
    loadComponent: () => import('./onboarding/onboarding').then((m) => m.Onboarding),
  },
  {
    path: 'avisos',
    loadComponent: () => import('./notifications/notifications').then((m) => m.Notifications),
  },
  { path: '**', redirectTo: 'hoje' },
];
