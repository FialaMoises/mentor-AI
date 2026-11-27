import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthApi } from '../core/auth-api';
import { amanhaIso, dataCurta, hojeIso } from '../core/datas';
import { mensagemDoErro } from '../core/erro';
import {
  AreaCatalogo,
  CompromissoExtraido,
  DocumentoOut,
  OnboardingApi,
  RotinaExtraida,
} from '../core/onboarding-api';
import { PlanApi } from '../core/plan-api';

type Passo = 'carregando' | 'questionario' | 'aviso' | 'upload' | 'conferencia' | 'pronto';

const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
/** O tipo do compromisso como se fala (o enum da API não tem acento). */
const TIPO: Record<string, string> = {
  aula: 'aula',
  plantao: 'plantão',
  academia: 'academia',
  trabalho: 'trabalho',
  leitura: 'leitura',
  outro: 'compromisso',
};

const DURACAO_MIN = 1;
const DURACAO_MAX = 24 * 60;

function duracaoValida(minutos: number): boolean {
  return Number.isInteger(minutos) && minutos >= DURACAO_MIN && minutos <= DURACAO_MAX;
}

@Component({
  selector: 'app-onboarding',
  imports: [FormsModule, RouterLink],
  templateUrl: './onboarding.html',
  styleUrl: './onboarding.scss',
})
export class Onboarding {
  private readonly destroyRef = inject(DestroyRef);
  private readonly api = inject(OnboardingApi);
  private readonly auth = inject(AuthApi);
  private readonly plano = inject(PlanApi);
  private readonly router = inject(Router);

  protected readonly dias = DIAS;
  protected readonly amanha = amanhaIso();
  /** Hoje do servidor (fuso do aluno): é com ele que o confirm decide o que entra. */
  protected readonly hoje = signal(hojeIso());
  /** Já tem perfil: veio da Minha rotina e pode voltar para lá. */
  protected readonly temPerfil = signal(false);
  /** O último confirm levou algum compromisso ou prova para o plano. */
  protected readonly entrouAlgo = signal(true);
  protected readonly dataCurta = dataCurta;
  protected readonly passo = signal<Passo>('carregando');
  protected readonly erro = signal<string | null>(null);
  protected readonly ocupado = signal(false);

  protected readonly areas = signal<AreaCatalogo[]>([]);
  protected readonly autoavaliacao = signal<Record<string, number>>({});

  protected fase: 'faculdade' | 'formado' = 'faculdade';
  protected modo: 'cursinho' | 'independente' = 'independente';
  protected horas = 14;
  protected provaNome = 'ENAMED';
  /** Signal, não campo: o `computed` abaixo precisa saber quando a data muda. */
  protected readonly provaData = signal('');

  protected readonly alunoId = signal<string | null>(null);
  protected readonly documento = signal<DocumentoOut | null>(null);
  protected readonly rotina = signal<RotinaExtraida | null>(null);
  protected readonly resumo = signal<string>('');
  protected tipoArquivo: 'grade' | 'escala' | 'cursinho' | 'outro' = 'grade';

  protected readonly podeEnviarQuestionario = computed(() => {
    const data = this.provaData();
    const avaliou = Object.keys(this.autoavaliacao()).length > 0;
    return data !== '' && data >= this.amanha && avaliou;
  });

  /** O que ainda falta para o Continuar, dito em texto ao lado do botão. */
  protected readonly faltaNoQuestionario = computed(() => {
    const data = this.provaData();
    if (!data) return 'Falta a data da prova.';
    if (data < this.amanha) return 'A data da prova precisa ser de amanhã em diante.';
    if (!Object.keys(this.autoavaliacao()).length) return 'Carregando as áreas…';
    return '';
  });

  /**
   * O que o confirm vai descartar, pelo mesmo critério do servidor (D3): data única
   * antes de hoje, semanal com vigência encerrada antes de hoje, prova que já passou.
   */
  protected passou(item: CompromissoExtraido): boolean {
    const hoje = this.hoje();
    if (item.on_day) return item.on_day < hoje;
    return !!item.ends_on && item.ends_on < hoje;
  }

  protected provaPassou(prova: { exam_date: string }): boolean {
    return prova.exam_date < this.hoje();
  }

  /** Nada do arquivo vale de hoje em diante: a tela avisa antes de confirmar. */
  protected readonly nadaVale = computed(() => {
    const rotina = this.rotina();
    if (!rotina) return false;
    const itens = rotina.commitments.length + rotina.exams.length;
    return (
      itens > 0 &&
      rotina.commitments.every((c) => this.passou(c)) &&
      rotina.exams.every((p) => this.provaPassou(p))
    );
  });

  /** "remover plantão Plantão extra, 15/01/2027": único por item para o leitor de tela. */
  protected rotuloRemover(item: CompromissoExtraido): string {
    const quando = item.on_day ? dataCurta(item.on_day) : (DIAS[item.weekday ?? 0] ?? '');
    const tipo = TIPO[item.kind] ?? item.kind;
    return `remover ${tipo} ${item.label || ''}`.trim() + `, ${quando}`;
  }

  /** Compromissos com duração fora de 1–1440 min: o confirmar espera a correção. */
  protected readonly duracoesInvalidas = computed(() =>
    (this.rotina()?.commitments ?? [])
      .filter((c) => !duracaoValida(c.duration_minutes))
      .map((c) => c.label || c.kind),
  );

  constructor() {
    this.api
      .catalogo()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (catalogo) => {
          this.areas.set(catalogo.areas);
          const inicial: Record<string, number> = {};
          for (const area of catalogo.areas) {
            inicial[area.slug] = 0.5;
          }
          this.autoavaliacao.set(inicial);
        },
        error: (falha) =>
          this.erro.set(mensagemDoErro(falha, 'Não consegui carregar as áreas. Tente de novo.')),
      });
    this.retomar();
  }

  /**
   * O passo vem do servidor, não da memória da aba: quem já tem perfil não volta
   * ao questionário (refazê-lo trocaria a autoavaliação), e recarregar a página
   * no meio do caminho retoma de onde parou.
   */
  private retomar(): void {
    this.auth
      .eu()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (eu) => {
          if (eu.today) this.hoje.set(eu.today);
          this.temPerfil.set(!eu.needs_onboarding);
          if (eu.needs_onboarding) this.passo.set('questionario');
          else if (eu.consent_required) this.passo.set('aviso');
          else this.passo.set('upload');
        },
        error: (falha) => {
          this.passo.set('questionario');
          this.erro.set(mensagemDoErro(falha, 'Não consegui ver onde você parou.'));
        },
      });
  }

  protected notaDa(areaSlug: string): number {
    return this.autoavaliacao()[areaSlug] ?? 0.5;
  }

  /** A nota de 0 a 100, sem o resto da conta em ponto flutuante (55.00000000000001). */
  protected notaEmPontos(areaSlug: string): number {
    return Math.round(this.notaDa(areaSlug) * 100);
  }

  protected mudarNota(areaSlug: string, valor: string): void {
    this.autoavaliacao.update((atual) => ({ ...atual, [areaSlug]: Number(valor) / 100 }));
  }

  protected enviarQuestionario(): void {
    if (this.ocupado() || !this.podeEnviarQuestionario()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.api
      .salvarPerfil({
        phase: this.fase,
        mode: this.modo,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Fortaleza',
        weekly_hours: this.horas,
        exams: [{ name: this.provaNome, exam_date: this.provaData(), is_primary: true }],
        self_assessment: this.autoavaliacao(),
      })
      .subscribe({
        next: (aluno) => {
          this.alunoId.set(aluno.id);
          this.ocupado.set(false);
          this.passo.set(aluno.consent_required ? 'aviso' : 'upload');
        },
        error: (falha) => {
          this.ocupado.set(false);
          this.erro.set(mensagemDoErro(falha, 'Não consegui criar seu perfil. Tente de novo.'));
        },
      });
  }

  protected aceitarAviso(): void {
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.api.aceitarAviso().subscribe({
      next: () => {
        this.ocupado.set(false);
        this.passo.set('upload');
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui registrar o aceite.'));
      },
    });
  }

  protected escolherArquivo(evento: Event): void {
    const entrada = evento.target as HTMLInputElement;
    const arquivo = entrada.files?.[0];
    if (!arquivo) return;

    this.ocupado.set(true);
    this.erro.set(null);
    this.api.enviarArquivo(arquivo, this.tipoArquivo).subscribe({
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
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(
          mensagemDoErro(
            falha,
            'O arquivo não foi aceito. Vale PDF, Word, Excel ou foto, até 10 MB.',
          ),
        );
      },
    });
  }

  /** Sem arquivo: o plano sai com o dia todo livre, e a rotina pode ser digitada depois. */
  protected seguirSemArquivo(): void {
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.erro.set(null);
    this.plano.replan().subscribe({
      next: () => {
        this.ocupado.set(false);
        void this.router.navigate(['/hoje']);
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui montar o plano agora.'));
      },
    });
  }

  protected removerCompromisso(indice: number): void {
    this.rotina.update((atual) =>
      atual ? { ...atual, commitments: atual.commitments.filter((_, i) => i !== indice) } : atual,
    );
  }

  protected removerProva(indice: number): void {
    this.rotina.update((atual) =>
      atual ? { ...atual, exams: atual.exams.filter((_, i) => i !== indice) } : atual,
    );
  }

  protected mudarDia(indice: number, valor: string): void {
    this.atualizarCompromisso(indice, { weekday: Number(valor), on_day: null });
  }

  protected mudarData(indice: number, valor: string): void {
    if (!valor) return;
    this.atualizarCompromisso(indice, { on_day: valor, weekday: null });
  }

  protected mudarInicio(indice: number, valor: string): void {
    this.atualizarCompromisso(indice, { starts_at: valor || null });
  }

  /** Campo vazio não vira 0: fica marcado como inválido até o aluno corrigir. */
  protected mudarDuracao(indice: number, valor: string): void {
    const minutos = valor.trim() === '' ? Number.NaN : Number(valor);
    this.atualizarCompromisso(indice, { duration_minutes: minutos });
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
    // Guarda de reentrada: o clique duplo chega antes de o botão ficar desabilitado.
    if (!documento || !rotina || this.ocupado() || this.duracoesInvalidas().length) return;

    this.ocupado.set(true);
    this.erro.set(null);
    const entrou = !this.nadaVale();
    this.api.confirmar(documento.id, rotina).subscribe({
      next: (confirmacao) => {
        this.ocupado.set(false);
        this.erro.set(null);
        this.resumo.set(confirmacao.replan_summary);
        this.entrouAlgo.set(entrou);
        this.passo.set('pronto');
      },
      error: (falha) => {
        this.ocupado.set(false);
        this.erro.set(mensagemDoErro(falha, 'Não consegui salvar a semana.'));
      },
    });
  }

  protected irParaHoje(): void {
    void this.router.navigate(['/hoje']);
  }
}
