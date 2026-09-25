import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { DayPlan, PlanTask, TaskStatus } from '../core/models';
import { OfflineQueue } from '../core/offline-queue';
import { PlanApi } from '../core/plan-api';

@Component({
  selector: 'app-today',
  imports: [FormsModule],
  templateUrl: './today.html',
  styleUrl: './today.scss',
})
export class Today implements OnDestroy {
  private readonly api = inject(PlanApi);
  private readonly fila = inject(OfflineQueue);

  protected readonly plan = signal<DayPlan | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly loading = signal(true);
  protected readonly offline = signal(!navigator.onLine);
  protected readonly pendentes = this.fila.pendentes;

  /** Tarefa de questões esperando o segundo toque: quantas acertou. */
  protected readonly lancando = signal<string | null>(null);
  protected acertos = 0;
  protected total = 20;

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
    this.api.today().subscribe({
      next: (plan) => {
        this.plan.set(plan);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Não consegui carregar a lista de hoje.');
        this.loading.set(false);
      },
    });
  }

  /** Primeiro toque: em questões, abre o lançamento; no resto, marca direto. */
  protected marcar(task: PlanTask, action: 'feita' | 'nao_deu'): void {
    if (action === 'feita' && task.kind === 'questoes' && this.lancando() !== task.id) {
      this.acertos = 0;
      this.total = 20;
      this.lancando.set(task.id);
      return;
    }
    this.enviar(task, action);
  }

  /** Segundo toque: confirma quantas acertou e marca a tarefa. */
  protected confirmarAcertos(task: PlanTask): void {
    this.enviar(task, 'feita', this.total, this.acertos);
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
        error: (falha: { status?: number }) => {
          // Sem rede a marcação fica na fila e sobe depois; erro do servidor desfaz.
          if (falha?.status && falha.status > 0) {
            this.fila.remover([marcacao.client_event_id]);
            this.patch(task.id, anterior);
            this.error.set('A marcação não foi salva. Tente de novo.');
          }
        },
      });
  }

  protected sincronizar(): void {
    const fila = this.fila.todas();
    if (!fila.length) return;

    this.api.sync(fila).subscribe({
      next: () => {
        this.fila.remover(fila.map((m) => m.client_event_id));
        this.load();
      },
      error: () => {
        // Continua na fila; tenta de novo na próxima volta da rede.
      },
    });
  }

  private patch(taskId: string, status: TaskStatus): void {
    this.plan.update((plan) =>
      plan
        ? { ...plan, tasks: plan.tasks.map((t) => (t.id === taskId ? { ...t, status } : t)) }
        : plan,
    );
  }
}
