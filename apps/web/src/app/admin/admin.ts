import { DecimalPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface Metricas {
  students: number;
  reached_week_three: number;
  active_week_three: number;
  retention_week_three: number;
  tasks_done_last_week: number;
  tasks_done_per_active_student: number;
  median_minutes_to_first_plan: number | null;
  students_logging_answers: number;
  answer_logging_rate: number;
  by_subscription_status: Record<string, number>;
}

/**
 * O painel do piloto. O token fica só nesta aba: não é para deixar salvo num
 * navegador que não seja o seu.
 */
@Component({
  selector: 'app-admin',
  imports: [FormsModule, DecimalPipe],
  templateUrl: './admin.html',
  styleUrl: './admin.scss',
})
export class Admin {
  private readonly http = inject(HttpClient);

  protected readonly metricas = signal<Metricas | null>(null);
  protected readonly erro = signal<string | null>(null);
  protected token = '';

  protected carregar(): void {
    this.erro.set(null);
    this.http
      .get<Metricas>('/api/v1/admin/metrics', { headers: { 'x-admin-token': this.token } })
      .subscribe({
        next: (dados) => this.metricas.set(dados),
        error: () => this.erro.set('Token recusado.'),
      });
  }

  protected porcentagem(valor: number): string {
    return `${Math.round(valor * 100)}%`;
  }

  protected statusList(mapa: Record<string, number>): { nome: string; total: number }[] {
    return Object.entries(mapa).map(([nome, total]) => ({ nome, total }));
  }
}
