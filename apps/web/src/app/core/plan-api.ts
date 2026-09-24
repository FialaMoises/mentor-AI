import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { DayPlan, PlanTask, ProgressInput } from './models';

/** Base da API. Em dev o proxy do `ng serve` manda /api para a API local. */
const API = '/api/v1';

@Injectable({ providedIn: 'root' })
export class PlanApi {
  private readonly http = inject(HttpClient);

  today(studentId: string): Observable<DayPlan> {
    return this.http.get<DayPlan>(`${API}/students/${studentId}/plan/today`);
  }

  markProgress(taskId: string, input: ProgressInput): Observable<PlanTask> {
    return this.http.post<PlanTask>(`${API}/tasks/${taskId}/progress`, input);
  }
}
