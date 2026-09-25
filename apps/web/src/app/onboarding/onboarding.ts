import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import {
  AreaCatalogo,
  CompromissoExtraido,
  DocumentoOut,
  OnboardingApi,
  RotinaExtraida,
} from '../core/onboarding-api';
import { Session } from '../core/session';

type Passo = 'questionario' | 'aviso' | 'upload' | 'conferencia' | 'pronto';

const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

@Component({
  selector: 'app-onboarding',
  imports: [FormsModule],
  templateUrl: './onboarding.html',
  styleUrl: './onboarding.scss',
})
export class Onboarding {
  private readonly api = inject(OnboardingApi);
  private readonly session = inject(Session);
  private readonly router = inject(Router);

  protected readonly dias = DIAS;
  protected readonly passo = signal<Passo>('questionario');
  protected readonly erro = signal<string | null>(null);
  protected readonly ocupado = signal(false);

  protected readonly areas = signal<AreaCatalogo[]>([]);
  protected readonly autoavaliacao = signal<Record<string, number>>({});

  protected fase: 'faculdade' | 'formado' = 'faculdade';
  protected modo: 'cursinho' | 'independente' = 'independente';
  protected horas = 14;
  protected provaNome = 'ENAMED';
  protected provaData = '';

  protected readonly alunoId = signal<string | null>(null);
  protected readonly documento = signal<DocumentoOut | null>(null);
  protected readonly rotina = signal<RotinaExtraida | null>(null);
  protected readonly resumo = signal<string>('');
  protected tipoArquivo: 'grade' | 'escala' | 'cursinho' | 'outro' = 'grade';

  protected readonly podeEnviarQuestionario = computed(
    () => this.provaData !== '' && Object.keys(this.autoavaliacao()).length > 0,
  );

  constructor() {
    this.api.catalogo().subscribe({
      next: (catalogo) => {
        this.areas.set(catalogo.areas);
        const inicial: Record<string, number> = {};
        for (const area of catalogo.areas) {
          inicial[area.slug] = 0.5;
        }
        this.autoavaliacao.set(inicial);
      },
      error: () => this.erro.set('Não consegui carregar as áreas. A API está de pé?'),
    });
  }

  protected notaDa(areaSlug: string): number {
    return this.autoavaliacao()[areaSlug] ?? 0.5;
  }

  protected mudarNota(areaSlug: string, valor: string): void {
    this.autoavaliacao.update((atual) => ({ ...atual, [areaSlug]: Number(valor) / 100 }));
  }

  protected enviarQuestionario(): void {
    this.ocupado.set(true);
    this.erro.set(null);
    this.api
      .criarAluno({
        phase: this.fase,
        mode: this.modo,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Fortaleza',
        weekly_hours: this.horas,
        exams: [{ name: this.provaNome, exam_date: this.provaData, is_primary: true }],
        self_assessment: this.autoavaliacao(),
      })
      .subscribe({
        next: (aluno) => {
          this.alunoId.set(aluno.id);
          this.session.studentId = aluno.id;
          this.ocupado.set(false);
          this.passo.set('aviso');
        },
        error: () => {
          this.ocupado.set(false);
          this.erro.set('Não consegui criar seu perfil. Confira a data da prova.');
        },
      });
  }

  protected aceitarAviso(): void {
    const id = this.alunoId();
    if (!id) return;
    this.ocupado.set(true);
    this.api.aceitarAviso(id).subscribe({
      next: () => {
        this.ocupado.set(false);
        this.passo.set('upload');
      },
      error: () => {
        this.ocupado.set(false);
        this.erro.set('Não consegui registrar o aceite.');
      },
    });
  }

  protected escolherArquivo(evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    const arquivo = entrada.files?.[0];
    const id = this.alunoId();
    if (!arquivo || !id) return;

    this.ocupado.set(true);
    this.erro.set(null);
    this.api.enviarArquivo(id, arquivo, this.tipoArquivo).subscribe({
      next: (documento) => {
        this.ocupado.set(false);
        this.documento.set(documento);
        if (documento.status === 'falhou' || !documento.extracted) {
          this.erro.set('Não consegui ler esse arquivo. Tente outro, ou siga sem ele.');
          return;
        }
        this.rotina.set(documento.extracted);
        this.passo.set('conferencia');
      },
      error: () => {
        this.ocupado.set(false);
        this.erro.set('O arquivo não foi aceito. Vale PDF, Word, Excel ou foto, até 10 MB.');
      },
    });
  }

  protected removerCompromisso(indice: number): void {
    this.rotina.update((atual) =>
      atual ? { ...atual, commitments: atual.commitments.filter((_, i) => i !== indice) } : atual,
    );
  }

  protected mudarDia(indice: number, valor: string): void {
    this.atualizarCompromisso(indice, { weekday: Number(valor) });
  }

  protected mudarDuracao(indice: number, valor: string): void {
    this.atualizarCompromisso(indice, { duration_minutes: Number(valor) });
  }

  private atualizarCompromisso(indice: number, mudanca: Partial<CompromissoExtraido>): void {
    this.rotina.update((atual) =>
      atual
        ? {
            ...atual,
            commitments: atual.commitments.map((c, i) => (i === indice ? { ...c, ...mudanca } : c)),
          }
        : atual,
    );
  }

  protected confirmar(): void {
    const documento = this.documento();
    const rotina = this.rotina();
    if (!documento || !rotina) return;

    this.ocupado.set(true);
    this.api.confirmar(documento.id, rotina).subscribe({
      next: (confirmacao) => {
        this.ocupado.set(false);
        this.resumo.set(confirmacao.replan_summary);
        this.passo.set('pronto');
      },
      error: () => {
        this.ocupado.set(false);
        this.erro.set('Não consegui salvar a semana.');
      },
    });
  }

  protected irParaHoje(): void {
    void this.router.navigate(['/hoje']);
  }
}
