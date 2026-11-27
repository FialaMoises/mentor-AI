/** Contas de horário "HH:MM" usadas pela rotina e pelo formulário de compromisso. */

export const DIA_MIN = 24 * 60;

/** "07:30" → 450. */
export function minutosDe(horario: string): number {
  const [h, m] = horario.split(':').map(Number);
  return h * 60 + m;
}

/** 450 → "07:30"; passa da meia-noite dando a volta no relógio. */
export function hhmm(minutos: number): string {
  const total = ((minutos % DIA_MIN) + DIA_MIN) % DIA_MIN;
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

/** Hora de fim de quem começa em `inicio` e dura `duracao` minutos. */
export function fimDe(inicio: string, duracao: number): string {
  return hhmm(minutosDe(inicio) + duracao);
}

/** Duração entre início e fim; fim antes do início = passa da meia-noite. */
export function duracaoEntre(inicio: string, fim: string): number {
  const duracao = minutosDe(fim) - minutosDe(inicio);
  return duracao <= 0 ? duracao + DIA_MIN : duracao;
}
