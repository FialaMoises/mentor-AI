import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const API = '/api/v1';

export interface SessaoOut {
  token: string;
  expires_at: string;
  student_id: string;
  needs_onboarding: boolean;
}

export interface EuOut {
  id: string;
  email: string | null;
  phase: string;
  mode: string;
  weekly_hours: number;
  needs_onboarding: boolean;
  subscription_status: string;
  trial_ends_on: string | null;
}

export interface AssinaturaOut {
  status: string;
  plan: string;
  price_cents: number;
  trial_ends_on: string | null;
  current_period_end: string | null;
  paused_until: string | null;
  has_access: boolean;
}

@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);

  pedirLink(email: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${API}/auth/magic-link`, { email });
  }

  entrar(token: string): Observable<SessaoOut> {
    return this.http.post<SessaoOut>(`${API}/auth/verify`, { token });
  }

  sair(): Observable<void> {
    return this.http.post<void>(`${API}/auth/logout`, {});
  }

  eu(): Observable<EuOut> {
    return this.http.get<EuOut>(`${API}/me`);
  }

  assinatura(): Observable<AssinaturaOut> {
    return this.http.get<AssinaturaOut>(`${API}/me/subscription`);
  }

  pagar(plan: 'mensal' | 'anual'): Observable<{ url: string; price_cents: number }> {
    return this.http.post<{ url: string; price_cents: number }>(
      `${API}/me/subscription/checkout`,
      { plan },
    );
  }

  pausar(until: string): Observable<AssinaturaOut> {
    return this.http.post<AssinaturaOut>(`${API}/me/subscription/pause`, { until });
  }

  retomar(): Observable<AssinaturaOut> {
    return this.http.post<AssinaturaOut>(`${API}/me/subscription/resume`, {});
  }

  cancelar(): Observable<AssinaturaOut> {
    return this.http.post<AssinaturaOut>(`${API}/me/subscription/cancel`, {});
  }

  exportarDados(): Observable<unknown> {
    return this.http.get(`${API}/me/export`);
  }

  apagarConta(): Observable<void> {
    return this.http.delete<void>(`${API}/me`);
  }
}
