/** Datas de calendário ("AAAA-MM-DD") no fuso do aparelho, sem passar por UTC. */

export function hojeIso(agora: Date = new Date()): string {
  return paraIso(agora);
}

export function amanhaIso(agora: Date = new Date()): string {
  const amanha = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate() + 1);
  return paraIso(amanha);
}

/** "2026-11-28" → "28/11/2026" (ou "28/11" sem o ano). */
export function dataCurta(iso: string | null | undefined, comAno = true): string {
  if (!iso) return '';
  const [a, m, d] = iso.slice(0, 10).split('-');
  return comAno ? `${d}/${m}/${a}` : `${d}/${m}`;
}

function paraIso(data: Date): string {
  const a = data.getFullYear();
  const m = String(data.getMonth() + 1).padStart(2, '0');
  const d = String(data.getDate()).padStart(2, '0');
  return `${a}-${m}-${d}`;
}

const SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

/** Soma dias a uma data de calendário, sem passar por fuso. */
export function somarDiasIso(iso: string, dias: number): string {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(Date.UTC(a, m - 1, d + dias)).toISOString().slice(0, 10);
}

/** "2026-11-30" → "seg, 30/11". */
export function diaComSemana(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number);
  const semana = SEMANA[new Date(Date.UTC(a, m - 1, d)).getUTCDay()];
  return `${semana}, ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
}
