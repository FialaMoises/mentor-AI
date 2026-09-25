import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { DayPlan, PlanTask, ProgressInput } from './models';
import { MarcacaoPendente } from './offline-queue';

/** Base da API. Em dev o proxy do `ng serve` manda /api para a API local. */
const API = '/api/v1';

export interface SyncResult {
  applied: number;
  duplicates: number;
  unknown: number;
}

export interface PushConfig {
  public_key: string;
  enabled: boolean;
}

@Injectable({ providedIn: 'root' })
export class PlanApi {
  private readonly http = inject(HttpClient);

  today(): Observable<DayPlan> {
    return this.http.get<DayPlan>(`${API}/me/plan/today`);
  }

  markProgress(taskId: string, input: ProgressInput): Observable<PlanTask> {
    return this.http.post<PlanTask>(`${API}/tasks/${taskId}/progress`, input);
  }

  sync(entries: MarcacaoPendente[]): Observable<SyncResult> {
    return this.http.post<SyncResult>(`${API}/me/progress/sync`, { entries });
  }

  pushConfig(): Observable<PushConfig> {
    return this.http.get<PushConfig>(`${API}/push/config`);
  }

  assinarPush(assinatura: PushSubscriptionJSON): Observable<unknown> {
    return this.http.post(`${API}/me/push-subscriptions`, {
      endpoint: assinatura.endpoint,
      keys: assinatura.keys,
    });
  }
}
