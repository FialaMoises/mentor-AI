import { TaskKind, TaskStatus } from './models';

/** O status da assinatura em palavras do aluno (a API manda o enum). */
const STATUS_ASSINATURA: Record<string, string> = {
  trial: 'Período de teste',
  ativa: 'Assinatura ativa',
  pausada: 'Assinatura pausada',
  cancelada: 'Assinatura cancelada',
  vencida: 'Assinatura vencida',
};

const TIPO_TAREFA: Record<TaskKind, string> = {
  teoria: 'Teoria',
  questoes: 'Questões',
  revisao: 'Revisão',
  simulado: 'Simulado',
};

const STATUS_TAREFA: Record<TaskStatus, string> = {
  pendente: 'pendente',
  feita: 'feita',
  nao_deu: 'não deu',
};

export function rotuloStatusAssinatura(status: string): string {
  return STATUS_ASSINATURA[status] ?? status;
}

export function rotuloTipoTarefa(tipo: string): string {
  return TIPO_TAREFA[tipo as TaskKind] ?? tipo;
}

export function rotuloStatusTarefa(status: TaskStatus): string {
  return STATUS_TAREFA[status] ?? status;
}
