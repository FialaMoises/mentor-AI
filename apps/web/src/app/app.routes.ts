import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'hoje' },
  {
    path: 'hoje',
    loadComponent: () => import('./today/today').then((m) => m.Today),
  },
  { path: '**', redirectTo: 'hoje' },
];
