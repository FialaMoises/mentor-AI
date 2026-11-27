import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnDestroy, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import { dataCurta, diaComSemana, hojeIso, somarDiasIso } from '../core/datas';
import { mensagemDoErro } from '../core/erro';
import { DayPlan, PlanTask, TaskStatus } from '../core/models';
import { OfflineQueue } from '../core/offline-queue';
import { PlanApi } from '../core/plan-api';
import { rotuloTipoTarefa } from '../core/rotulos';

@Component({
  selector: 'app-today',
  imports: [FormsModule],
  templateUrl: './today.html',
  styleUrl: './today.scss',
})
export class Today implements OnDestroy {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(PlanApi);
  private readonly fila = inject(OfflineQueue);

  protected readonly plan = signal<DayPlan | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly loading = signal(true);
  protected readonly offline = signal(!navigator.onLine);
  protected readonly pendentes = this.fila.pendentes;
  /** Marcações feitas sem internet que o servidor não aceitou (saíram da fila). */
  protected readonly avisoFila = signal<string | null>(null);

  /**
   * A lista veio de outro dia: o service worker devolve a última guardada quando
   * não há rede. A tela diz de que dia ela é, em vez de fingir que é a de hoje.
   */
  protected readonly diaDaLista = computed(() => {
    const plan = this.plan();
    return plan && plan.date !== hojeIso() ? dataCurta(plan.date, false) : null;
  });

  /** Tarefa de questões esperando o segundo toque: quantas acertou. */
  protected readonly lancando = signal<string | null>(null);
  protected readonly acertos = signal(0);
  protected readonly total = signal(20);

  /** Acertos acima do total não são cortados em silêncio: a tela pede a correção. */
  protected readonly erroAcertos = computed(() => {
    const acertos = Number(this.acertos());
    const total = Number(this.total());
    if (!Number.isInteger(total) || total < 1)
      return 'O total de questões precisa ser de 1 para cima.';
    if (!Number.isInteger(acertos) || acertos < 0) return 'Os acertos precisam ser 0 ou mais.';
    if (acertos > total)
      return `${acertos} acertos de ${total} questões não fecha: confira os números.`;
    return null;
  });

  /** "amanhã" quando o plano começa no dia seguinte; senão, o dia ("seg, 30/11"). */
  protected readonly inicioDoPlano = computed(() => {
    const plan = this.plan();
    if (!plan?.plan_starts_on) return '';
    return plan.plan_starts_on === somarDiasIso(plan.date, 1)
      ? 'amanhã'
      : diaComSemana(plan.plan_starts_on);
  });

  /** Primeiro dia: o plano existe, mas a primeira tarefa é de amanhã em diante. */
  protected readonly planoComecaDepois = computed(() => {
    const plan = this.plan();
    return !!plan?.plan_starts_on && plan.plan_starts_on > plan.date;
  });

  protected readonly done = computed(
    () => this.plan()?.tasks.filter((t) => t.status === 'feita').length ?? 0,
  );
  protected readonly total_tarefas = computed(() => this.plan()?.tasks.length ?? 0);

  private readonly aoVoltarOnline = () => {
    this.offline.set(false);
    this.sincronizar();
  };
  private readonly aoCairOffline = () => this.offline.set(true);

  constructor() {
    window.addEventListener('online', this.aoVoltarOnline);
    window.addEventListener('offline', this.aoCairOffline);
    this.load();
    this.sincronizar();
  }

  ngOnDestroy(): void {
    window.removeEventListener('online', this.aoVoltarOnline);
    window.removeEventListener('offline', this.aoCairOffline);
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .today()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (plan) => {
          this.plan.set(plan);
          this.loading.set(false);
        },
        error: (falha) => {
          this.error.set(mensagemDoErro(falha, 'Não consegui carregar a lista de hoje.'));
          this.loading.set(false);
        },
      });
  }

  protected tipo(kind: string): string {
    return rotuloTipoTarefa(kind);
  }

  /** "Insuficiência cardíaca (Teoria)": o leitor de tela sabe de qual tarefa é o botão. */
  protected rotulo(task: PlanTask): string {
    return `${task.topic} (${rotuloTipoTarefa(task.kind)})`;
  }

  /** Primeiro toque: em questões, abre o lançamento; no resto, marca direto. */
  protected marcar(task: PlanTask, action: 'feita' | 'nao_deu'): void {
    if (action === 'feita' && task.kind === 'questoes' && this.lancando() !== task.id) {
      this.acertos.set(0);
      this.total.set(20);
      this.lancando.set(task.id);
      return;
    }
    this.enviar(task, action);
  }

  /** Segundo toque: confirma quantas acertou e marca a tarefa. */
  protected confirmarAcertos(task: PlanTask): void {
    // O `[max]` do input não segura o ngModel: o limite vale aqui, antes da fila.
    if (this.erroAcertos()) return;
    this.enviar(task, 'feita', Number(this.total()), Number(this.acertos()));
    this.lancando.set(null);
  }

  protected pularAcertos(task: PlanTask): void {
    this.enviar(task, 'feita');
    this.lancando.set(null);
  }

  private enviar(
    task: PlanTask,
    action: 'feita' | 'nao_deu',
    answered?: number,
    correct?: number,
  ): void {
    const anterior = task.status;
    this.error.set(null);
    this.patch(task.id, action);

    const marcacao = this.fila.enfileirar({
      task_id: task.id,
      action,
      answered: answered ?? null,
      correct: correct ?? null,
    });

    this.api
      .markProgress(task.id, {
        action,
        answered: answered ?? null,
        correct: correct ?? null,
        client_event_id: marcacao.client_event_id,
      })
      .subscribe({
        next: () => this.fila.remover([marcacao.client_event_id]),
        error: (falha: HttpErrorResponse) => {
          // Sem rede a marcação fica na fila e sobe depois; erro do servidor desfaz.
          if (falha?.status && falha.status > 0) {
            this.fila.remover([marcacao.client_event_id]);
            this.patch(task.id, anterior);
            this.error.set(mensagemDoErro(falha, 'A marcação não foi salva. Tente de novo.'));
          }
        },
      });
  }

  protected sincronizar(): void {
    const fila = this.fila.todas();
    if (!fila.length) return;

    const ids = fila.map((m) => m.client_event_id);
    this.api.sync(fila).subscribe({
      next: (resultado) => {
        // Cada entrada teve um destino final (aplicada, repetida, desconhecida ou
        // recusada): a fila inteira sai. As que não valeram ganham um aviso.
        this.fila.remover(ids);
        const perdidas =
          (resultado.unknown ?? 0) + (resultado.rejected ?? 0) + (resultado.stale ?? 0);
        this.avisoFila.set(perdidas > 0 ? this.textoPerdidas(perdidas) : null);
        this.load();
      },
      error: (falha: HttpErrorResponse) => {
        const status = falha?.status ?? 0;
        // Sem rede, erro do servidor (5xx) ou sessão caída (401): continua na fila
        // e tenta de novo na próxima volta da rede. Um 4xx é recusa de vez.
        if (status === 0 || status >= 500 || status === 401) return;
        this.fila.remover(ids);
        this.avisoFila.set(this.textoPerdidas(ids.length));
      },
    });
  }

  private textoPerdidas(n: number): string {
    return n === 1
      ? '1 marcação feita sem internet não pôde ser salva: marque essa tarefa de novo.'
      : `${n} marcações feitas sem internet não puderam ser salvas: marque essas tarefas de novo.`;
  }

  private patch(taskId: string, status: TaskStatus): void {
    this.plan.update((plan) =>
      plan
        ? { ...plan, tasks: plan.tasks.map((t) => (t.id === taskId ? { ...t, status } : t)) }
        : plan,
    );
  }
}
