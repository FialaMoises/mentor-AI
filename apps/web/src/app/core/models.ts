export type TaskKind = 'teoria' | 'questoes' | 'revisao' | 'simulado';
export type TaskStatus = 'pendente' | 'feita' | 'nao_deu';

export interface PlanTask {
  id: string;
  kind: TaskKind;
  topic: string;
  minutes: number;
  status: TaskStatus;
}

export interface DayPlan {
  date: string;
  capacity_minutes: number;
  light: boolean;
  plan_version: number;
  /** Primeiro dia com tarefa no plano; depois de hoje = o plano ainda não começou. */
  plan_starts_on?: string | null;
  tasks: PlanTask[];
}

export interface ProgressInput {
  action: 'feita' | 'nao_deu';
  answered?: number | null;
  correct?: number | null;
  client_event_id?: string;
}
