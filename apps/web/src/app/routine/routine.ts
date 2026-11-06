import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import {
  RoutineApi,
  RoutineDay,
  RoutineItem,
  RoutineWeek,
  SaveResult,
  SeriesInput,
} from '../core/routine-api';
import { CommitmentForm, DIAS_CURTOS, FormInicial } from './commitment-form';

/** Altura de uma hora na linha do tempo. O dia inteiro (0h–24h) fica visível. */
const HORA_PX = 22;
const DIA_MIN = 24 * 60;

interface Bloco {
  item: RoutineItem;
  topo: number;
  altura: number;
  /** Pedaço de um compromisso que começou no dia anterior e passou da meia-noite. */
  continua: boolean;
}

interface Edicao {
  seriesId: string | null;
  inicial: FormInicial | null;
}

function minutos(horario: string): number {
  const [h, m] = horario.split(':').map(Number);
  return h * 60 + m;
}

/** Soma dias a uma data ISO sem passar por fuso: a data é só calendário. */
function somarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.split('-').map(Number);
  const data = new Date(Date.UTC(a, m - 1, d + dias));
  return data.toISOString().slice(0, 10);
}

@Component({
  selector: 'app-routine',
  imports: [RouterLink, CommitmentForm],
  templateUrl: './routine.html',
  styleUrl: './routine.scss',
})
export class Routine implements OnDestroy {
  private readonly api = inject(RoutineApi);

  protected readonly diasCurtos = DIAS_CURTOS;
  protected readonly horas = Array.from({ length: 24 }, (_, h) => h);
  protected readonly alturaDia = 24 * HORA_PX;
  protected readonly horaPx = HORA_PX;

  protected readonly semana = signal<RoutineWeek | null>(null);
  protected readonly carregando = signal(true);
  protected readonly erro = signal<string | null>(null);
  protected readonly resumo = signal<string | null>(null);
  protected readonly salvando = signal(false);
  protected readonly offline = signal(!navigator.onLine);
  protected readonly diaSelecionado = signal(0);
  protected readonly edicao = signal<Edicao | null>(null);
  /**
   * A edição aberta como lista de um item: trocar de bloco gera um objeto novo e
   * o `@for` recria o formulário, em vez de reaproveitar os campos do anterior.
   */
  protected readonly edicoes = computed(() => {
    const atual = this.edicao();
    return atual ? [atual] : [];
  });

  protected readonly faixaSemHorario = computed(() => {
    const maior = Math.max(
      0,
      ...(this.semana()?.days ?? []).map((d) => d.items.filter((i) => !i.starts_at).length),
    );
    return maior * 1.75;
  });

  protected readonly periodo = computed(() => {
    const semana = this.semana();
    if (!semana) return '';
    const fim = somarDias(semana.week_start, 6);
    return `${this.diaMes(semana.week_start)} a ${this.diaMes(fim)}`;
  });

  private readonly aoVoltarOnline = () => this.offline.set(false);
  private readonly aoCairOffline = () => this.offline.set(true);

  constructor() {
    window.addEventListener('online', this.aoVoltarOnline);
    window.addEventListener('offline', this.aoCairOffline);
    this.carregar();
  }

  ngOnDestroy(): void {
    window.removeEventListener('online', this.aoVoltarOnline);
    window.removeEventListener('offline', this.aoCairOffline);
  }

  protected carregar(semanaDe?: string): void {
    this.carregando.set(true);
    this.api.week(semanaDe).subscribe({
      next: (semana) => {
        this.semana.set(semana);
        this.carregando.set(false);
        this.erro.set(null);
        const hoje = semana.days.findIndex((d) => d.day === semana.today);
        this.diaSelecionado.set(hoje >= 0 ? hoje : 0);
      },
      error: () => {
        this.carregando.set(false);
        this.erro.set('Não consegui carregar a sua rotina.');
      },
    });
  }

  protected mudarSemana(passo: number): void {
    const semana = this.semana();
    if (!semana) return;
    this.resumo.set(null);
    this.carregar(somarDias(semana.week_start, 7 * passo));
  }

  protected diaMes(iso: string): string {
    const [, m, d] = iso.split('-');
    return `${d}/${m}`;
  }

  protected rodape(dia: RoutineDay): string {
    if (dia.light) return 'dia leve';
    if (dia.free_minutes <= 0) return 'estudo: 0';
    const h = Math.floor(dia.free_minutes / 60);
    const m = dia.free_minutes % 60;
    if (!h) return `estudo: ${m}min`;
    return m ? `estudo: ${h}h ${String(m).padStart(2, '0')}min` : `estudo: ${h}h`;
  }

  protected semHorario(dia: RoutineDay): RoutineItem[] {
    return dia.items.filter((i) => !i.starts_at);
  }

  protected blocos(indice: number): Bloco[] {
    const dias = this.semana()?.days ?? [];
    const saida: Bloco[] = [];
    const anterior = indice > 0 ? dias[indice - 1] : null;
    for (const item of anterior?.items ?? []) {
      if (!item.starts_at) continue;
      const sobra = minutos(item.starts_at) + item.duration_minutes - DIA_MIN;
      if (sobra > 0) {
        saida.push({
          item,
          topo: 0,
          altura: (Math.min(sobra, DIA_MIN) * HORA_PX) / 60,
          continua: true,
        });
      }
    }
    for (const item of dias[indice]?.items ?? []) {
      if (!item.starts_at) continue;
      const inicio = minutos(item.starts_at);
      const duracao = Math.min(item.duration_minutes, DIA_MIN - inicio);
      saida.push({
        item,
        topo: (inicio * HORA_PX) / 60,
        altura: Math.max((duracao * HORA_PX) / 60, 14),
        continua: false,
      });
    }
    return saida;
  }

  protected fim(item: RoutineItem): string {
    if (!item.starts_at) return '';
    const total = (minutos(item.starts_at) + item.duration_minutes) % DIA_MIN;
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  protected adicionar(): void {
    this.resumo.set(null);
    this.edicao.set({ seriesId: null, inicial: null });
  }

  /**
   * Abre a edição com a série como ela vale de amanhã em diante — vinda do
   * servidor, nunca deduzida da semana exibida (que pode mostrar só parte dos
   * dias, ou uma versão que já foi encerrada).
   */
  protected abrir(item: RoutineItem): void {
    if (!item.editable || !item.series) return;
    this.resumo.set(null);
    this.edicao.set({
      seriesId: item.series_id,
      inicial: { origem: item.document_name, input: { ...item.series } },
    });
  }

  protected fechar(): void {
    this.edicao.set(null);
  }

  protected salvar(entrada: SeriesInput): void {
    const edicao = this.edicao();
    if (!edicao) return;
    const pedido = edicao.seriesId
      ? this.api.update(edicao.seriesId, entrada)
      : this.api.create(entrada);
    this.enviar(pedido);
  }

  protected apagar(): void {
    const seriesId = this.edicao()?.seriesId;
    if (seriesId) this.enviar(this.api.remove(seriesId));
  }

  private enviar(pedido: Observable<SaveResult>): void {
    if (this.salvando()) return;
    this.salvando.set(true);
    this.erro.set(null);
    pedido.subscribe({
      next: (resultado) => {
        this.salvando.set(false);
        this.edicao.set(null);
        this.resumo.set(resultado.replan_summary || 'Rotina salva. Vale de amanhã em diante.');
        this.carregar(this.semana()?.week_start);
      },
      error: (falha: HttpErrorResponse) => {
        this.salvando.set(false);
        // O servidor explica em português o que recusou; sem explicação, a genérica.
        const detalhe: unknown = falha.error?.detail;
        this.erro.set(
          typeof detalhe === 'string' && detalhe
            ? detalhe
            : 'Não consegui salvar. Confira os campos e tente de novo.',
        );
      },
    });
  }
}
