import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnDestroy, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { EMPTY, Observable, Subject, catchError, switchMap } from 'rxjs';

import { mensagemDoErro } from '../core/erro';
import { DIA_MIN, fimDe, minutosDe } from '../core/horario';
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

interface Bloco {
  item: RoutineItem;
  topo: number;
  altura: number;
  /** Pedaço de um compromisso que começou no dia anterior e passou da meia-noite. */
  continua: boolean;
  /** Coluna do bloco entre os que se sobrepõem, e quantas colunas o grupo tem. */
  coluna: number;
  colunas: number;
}

interface Edicao {
  /** Muda a cada abertura: o `@for` recria o formulário sem rastrear por identidade. */
  id: number;
  seriesId: string | null;
  inicial: FormInicial | null;
}

/**
 * Blocos que se sobrepõem dividem a largura da coluna: cada grupo de blocos que
 * se tocam ganha tantas colunas quantas precisar, e cada bloco fica numa delas.
 * Sem isso o de cima cobre o de baixo e o de baixo nem pode ser clicado.
 */
function distribuirColunas(blocos: Bloco[]): Bloco[] {
  const ordenados = [...blocos].sort((a, b) => a.topo - b.topo || b.altura - a.altura);
  let grupo: Bloco[] = [];
  let fimDoGrupo = -1;
  const fechar = () => {
    const colunas = Math.max(1, ...grupo.map((b) => b.coluna + 1));
    for (const b of grupo) b.colunas = colunas;
    grupo = [];
  };
  for (const bloco of ordenados) {
    if (grupo.length && bloco.topo >= fimDoGrupo) fechar();
    const ocupadas = new Set(
      grupo.filter((b) => b.topo + b.altura > bloco.topo).map((b) => b.coluna),
    );
    let coluna = 0;
    while (ocupadas.has(coluna)) coluna++;
    bloco.coluna = coluna;
    grupo.push(bloco);
    fimDoGrupo = Math.max(fimDoGrupo, bloco.topo + bloco.altura);
  }
  if (grupo.length) fechar();
  return ordenados;
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
  private readonly destroyRef = inject(DestroyRef);
  /** Semana pedida por último: só a resposta dela chega à tela (switchMap). */
  private readonly pedidos = new Subject<string | undefined>();
  private semanaPedida: string | undefined;
  /** Quem abriu o formulário: o foco volta para lá ao fechar. */
  private origemDoFoco: HTMLElement | null = null;
  private proximaEdicao = 0;

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

  /**
   * Quantos chips "sem horário" cabem na faixa (o maior dia da semana). A altura
   * vem do CSS (`--chips` × `--chip-h`), a mesma nas duas colunas, no celular e no
   * desktop: assim a linha do tempo das horas e a do dia começam no mesmo ponto.
   */
  protected readonly faixaSemHorario = computed(() =>
    Math.max(
      0,
      ...(this.semana()?.days ?? []).map((d) => d.items.filter((i) => !i.starts_at).length),
    ),
  );

  protected readonly periodo = computed(() => {
    const semana = this.semana();
    if (!semana) return '';
    const fim = somarDias(semana.week_start, 6);
    return `${this.diaMes(semana.week_start)} a ${this.diaMes(fim)}`;
  });

  /** Data única e vigência começam amanhã: hoje é congelado. */
  protected readonly amanha = computed(() => {
    const hoje = this.semana()?.today;
    return hoje ? somarDias(hoje, 1) : '';
  });

  private readonly aoVoltarOnline = () => this.offline.set(false);
  private readonly aoCairOffline = () => this.offline.set(true);

  constructor() {
    window.addEventListener('online', this.aoVoltarOnline);
    window.addEventListener('offline', this.aoCairOffline);
    this.pedidos
      .pipe(
        // O erro fica dentro do switchMap: um GET que falha não encerra a escuta, e
        // a próxima troca de semana (ou o recarregar depois de salvar) ainda funciona.
        switchMap((semanaDe) =>
          this.api.week(semanaDe).pipe(
            catchError((falha) => {
              this.carregando.set(false);
              this.semanaPedida = this.semana()?.week_start;
              this.erro.set(mensagemDoErro(falha, 'Não consegui carregar a sua rotina.'));
              return EMPTY;
            }),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (semana) => {
          this.semana.set(semana);
          this.semanaPedida = semana.week_start;
          this.carregando.set(false);
          this.erro.set(null);
          const hoje = semana.days.findIndex((d) => d.day === semana.today);
          this.diaSelecionado.set(hoje >= 0 ? hoje : 0);
        },
      });
    this.carregar();
  }

  ngOnDestroy(): void {
    window.removeEventListener('online', this.aoVoltarOnline);
    window.removeEventListener('offline', this.aoCairOffline);
  }

  protected carregar(semanaDe?: string): void {
    this.carregando.set(true);
    this.semanaPedida = semanaDe ?? this.semanaPedida;
    this.pedidos.next(semanaDe);
  }

  /** Anda a partir da última semana pedida: dois cliques rápidos andam duas semanas. */
  protected mudarSemana(passo: number): void {
    const base = this.semanaPedida ?? this.semana()?.week_start;
    if (!base) return;
    this.resumo.set(null);
    this.carregar(somarDias(base, 7 * passo));
  }

  protected diaMes(iso: string): string {
    const [, m, d] = iso.split('-');
    return `${d}/${m}`;
  }

  protected rodape(dia: RoutineDay): string {
    if (dia.light) return 'dia leve';
    if (dia.free_minutes <= 0) return 'estudo: 0h';
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
      const sobra = minutosDe(item.starts_at) + item.duration_minutes - DIA_MIN;
      if (sobra > 0) {
        saida.push({
          item,
          topo: 0,
          altura: (Math.min(sobra, DIA_MIN) * HORA_PX) / 60,
          continua: true,
          coluna: 0,
          colunas: 1,
        });
      }
    }
    for (const item of dias[indice]?.items ?? []) {
      if (!item.starts_at) continue;
      const inicio = minutosDe(item.starts_at);
      const duracao = Math.min(item.duration_minutes, DIA_MIN - inicio);
      saida.push({
        item,
        topo: (inicio * HORA_PX) / 60,
        altura: Math.max((duracao * HORA_PX) / 60, 14),
        continua: false,
        coluna: 0,
        colunas: 1,
      });
    }
    return distribuirColunas(saida);
  }

  protected fim(item: RoutineItem): string {
    if (!item.starts_at) return '';
    return fimDe(item.starts_at, item.duration_minutes);
  }

  /** Posição e largura do bloco na coluna do dia, em porcentagem. */
  protected esquerda(b: Bloco): string {
    return `calc(${(b.coluna * 100) / b.colunas}% + 2px)`;
  }

  protected largura(b: Bloco): string {
    return `calc(${100 / b.colunas}% - 4px)`;
  }

  protected adicionar(): void {
    this.resumo.set(null);
    this.guardarOrigemDoFoco();
    this.edicao.set({ id: ++this.proximaEdicao, seriesId: null, inicial: null });
  }

  /**
   * Abre a edição com a série como ela vale de amanhã em diante — vinda do
   * servidor, nunca deduzida da semana exibida (que pode mostrar só parte dos
   * dias, ou uma versão que já foi encerrada).
   */
  protected abrir(item: RoutineItem): void {
    if (!item.editable || !item.series) {
      this.resumo.set(
        `${item.label || item.kind}: essa versão já terminou, então não dá para mudar. ` +
          'O que vale de amanhã em diante aparece nas semanas seguintes.',
      );
      return;
    }
    this.resumo.set(null);
    this.guardarOrigemDoFoco();
    this.edicao.set({
      id: ++this.proximaEdicao,
      seriesId: item.series_id,
      inicial: { origem: item.document_name, input: { ...item.series } },
    });
  }

  protected fechar(): void {
    this.edicao.set(null);
    this.devolverFoco();
  }

  private guardarOrigemDoFoco(): void {
    const ativo = document.activeElement;
    // Quem já está dentro do formulário não é origem: trocar de bloco mantém a antiga.
    if (ativo instanceof HTMLElement && !ativo.closest('.formulario')) {
      this.origemDoFoco = ativo;
    }
  }

  /** O foco volta para o bloco ou para o "+ adicionar", não para o topo da página. */
  private devolverFoco(): void {
    const origem = this.origemDoFoco;
    this.origemDoFoco = null;
    setTimeout(() => {
      const alvo =
        origem && origem.isConnected
          ? origem
          : (document.querySelector('app-routine button.adicionar') as HTMLElement | null);
      alvo?.focus();
    });
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
        this.devolverFoco();
        this.resumo.set(resultado.replan_summary || 'Rotina salva. Vale de amanhã em diante.');
        this.carregar(this.semana()?.week_start);
      },
      error: (falha: HttpErrorResponse) => {
        this.salvando.set(false);
        // O servidor explica em português o que recusou; sem explicação, a genérica.
        this.erro.set(
          mensagemDoErro(falha, 'Não consegui salvar. Confira os campos e tente de novo.'),
        );
      },
    });
  }
}
