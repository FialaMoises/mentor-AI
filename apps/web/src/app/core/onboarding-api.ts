import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

const API = '/api/v1';

export interface AreaCatalogo {
  slug: string;
  name: string;
  temas: { slug: string; name: string; subtemas: { slug: string; name: string }[] }[];
}

export interface Catalogo {
  exam: string;
  exam_name: string;
  weights_source: string;
  areas: AreaCatalogo[];
}

export interface QuestionarioInput {
  phase: 'faculdade' | 'formado';
  mode: 'cursinho' | 'independente';
  timezone: string;
  weekly_hours: number;
  exams: { name: string; exam_date: string; is_primary: boolean }[];
  self_assessment: Record<string, number>;
}

export interface AlunoCriado {
  id: string;
  phase: string;
  mode: string;
  weekly_hours: number;
  topics_assessed: number;
  consent_required: boolean;
}

export interface CompromissoExtraido {
  kind: 'aula' | 'plantao' | 'academia' | 'trabalho' | 'outro';
  label: string;
  weekday: number | null;
  on_day: string | null;
  duration_minutes: number;
  starts_on: string | null;
  ends_on: string | null;
}

export interface RotinaExtraida {
  commitments: CompromissoExtraido[];
  exams: { name: string; exam_date: string }[];
  unreadable: string[];
}

export interface DocumentoOut {
  id: string;
  kind: string;
  original_name: string;
  status: 'recebido' | 'extraido' | 'confirmado' | 'falhou';
  error: string;
  extracted: RotinaExtraida | null;
  original_kept: boolean;
}

export interface ConfirmacaoOut {
  document: DocumentoOut;
  commitments: number;
  days_recalculated: number;
  replan_summary: string;
}

@Injectable({ providedIn: 'root' })
export class OnboardingApi {
  private readonly http = inject(HttpClient);

  catalogo(prova = 'enamed'): Observable<Catalogo> {
    return this.http.get<Catalogo>(`${API}/catalog/${prova}`);
  }

  criarAluno(entrada: QuestionarioInput): Observable<AlunoCriado> {
    return this.http.post<AlunoCriado>(`${API}/students`, entrada);
  }

  aceitarAviso(studentId: string): Observable<{ accepted: boolean; policy_version: string }> {
    return this.http.post<{ accepted: boolean; policy_version: string }>(
      `${API}/students/${studentId}/consent`,
      {},
    );
  }

  enviarArquivo(studentId: string, arquivo: File, kind: string): Observable<DocumentoOut> {
    const corpo = new FormData();
    corpo.append('file', arquivo);
    corpo.append('kind', kind);
    return this.http.post<DocumentoOut>(`${API}/students/${studentId}/documents`, corpo);
  }

  confirmar(documentId: string, rotina: RotinaExtraida): Observable<ConfirmacaoOut> {
    return this.http.post<ConfirmacaoOut>(`${API}/documents/${documentId}/confirm`, rotina);
  }
}
