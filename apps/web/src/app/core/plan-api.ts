import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api-base';
import { DayPlan, PlanTask, ProgressInput } from './models';
import { MarcacaoPendente } from './offline-queue';

export interface SyncResult {
  applied: number;
  duplicates: number;
  unknown: number;
  /** Recusadas de vez pelo servidor (acertos acima das questões, por exemplo). */
  rejected: number;
  /** Mais velhas que a última marcação da tarefa: ficaram só no histórico. */
  stale?: number;
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

  /** Refaz o plano sem arquivo novo: o aluno seguiu sem enviar a rotina. */
  replan(): Observable<{ plan_version: number; summary: string }> {
    return this.http.post<{ plan_version: number; summary: string }>(`${API}/me/plan/replan`, {});
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
