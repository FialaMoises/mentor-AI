import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const API = '/api/v1';

export type CommitmentKind = 'aula' | 'plantao' | 'academia' | 'trabalho' | 'leitura' | 'outro';

export interface RoutineItem {
  series_id: string;
  kind: CommitmentKind;
  label: string;
  /** "HH:MM", ou null quando não se sabe o horário. */
  starts_at: string | null;
  duration_minutes: number;
  recurring: boolean;
  document_name: string | null;
  edited_by_student: boolean;
  editable: boolean;
  ends_on: string | null;
  /** O que a série vale de amanhã em diante; é isto que a edição abre. null = encerrada. */
  series: SeriesInput | null;
}

export interface RoutineDay {
  day: string;
  free_minutes: number;
  light: boolean;
  computed: boolean;
  items: RoutineItem[];
}

export interface RoutineWeek {
  week_start: string;
  today: string;
  changed_today: boolean;
  days: RoutineDay[];
}

export interface SeriesInput {
  kind: CommitmentKind;
  label: string;
  weekdays: number[];
  on_day: string | null;
  starts_at: string | null;
  duration_minutes: number;
  starts_on: string | null;
  ends_on: string | null;
}

export interface SaveResult {
  series_id: string | null;
  replan_summary: string;
}

@Injectable({ providedIn: 'root' })
export class RoutineApi {
  private readonly http = inject(HttpClient);

  week(weekOf?: string): Observable<RoutineWeek> {
    const params = weekOf ? new HttpParams().set('week', weekOf) : undefined;
    return this.http.get<RoutineWeek>(`${API}/me/routine`, { params });
  }

  create(input: SeriesInput): Observable<SaveResult> {
    return this.http.post<SaveResult>(`${API}/me/commitment-series`, input);
  }

  update(seriesId: string, input: SeriesInput): Observable<SaveResult> {
    return this.http.patch<SaveResult>(`${API}/me/commitment-series/${seriesId}`, input);
  }

  remove(seriesId: string): Observable<SaveResult> {
    return this.http.delete<SaveResult>(`${API}/me/commitment-series/${seriesId}`);
  }
}
