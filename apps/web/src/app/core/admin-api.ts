import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API } from './api-base';

export interface Metricas {
  students: number;
  reached_week_three: number;
  active_week_three: number;
  retention_week_three: number;
  tasks_done_last_week: number;
  tasks_done_per_active_student: number;
  median_minutes_to_first_plan: number | null;
  students_logging_answers: number;
  answer_logging_rate: number;
  by_subscription_status: Record<string, number>;
}

/** O painel do piloto. O token do operador vai por cabeçalho e não é guardado. */
@Injectable({ providedIn: 'root' })
export class AdminApi {
  private readonly http = inject(HttpClient);

  metricas(token: string): Observable<Metricas> {
    return this.http.get<Metricas>(`${API}/admin/metrics`, {
      headers: { 'x-admin-token': token },
    });
  }
}
