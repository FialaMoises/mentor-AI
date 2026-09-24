import { Component, computed, inject, signal } from '@angular/core';

import { SEED_STUDENT_ID } from '../core/config';
import { DayPlan, PlanTask, TaskStatus } from '../core/models';
import { PlanApi } from '../core/plan-api';

@Component({
  selector: 'app-today',
  templateUrl: './today.html',
  styleUrl: './today.scss',
})
export class Today {
  private readonly api = inject(PlanApi);

  protected readonly plan = signal<DayPlan | null>(null);
  protected readonly error = signal<string | null>(null);
  protected readonly loading = signal(true);

  protected readonly done = computed(
    () => this.plan()?.tasks.filter((t) => t.status === 'feita').length ?? 0,
  );
  protected readonly total = computed(() => this.plan()?.tasks.length ?? 0);

  constructor() {
    this.load();
  }

  protected load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.today(SEED_STUDENT_ID).subscribe({
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

  protected mark(task: PlanTask, action: 'feita' | 'nao_deu'): void {
    const previous = task.status;
    this.patch(task.id, action);
    this.api.markProgress(task.id, { action }).subscribe({
      error: () => {
        this.patch(task.id, previous);
        this.error.set('A marcação não foi salva. Tente de novo.');
      },
    });
  }

  private patch(taskId: string, status: TaskStatus): void {
    this.plan.update((plan) =>
      plan
        ? {
            ...plan,
            tasks: plan.tasks.map((t) => (t.id === taskId ? { ...t, status } : t)),
          }
        : plan,
    );
  }
}
