import { Component, OnInit, computed, input, output, signal } from '@angular/core';

import { CommitmentKind, SeriesInput } from '../core/routine-api';

export const TIPOS: { valor: CommitmentKind; nome: string }[] = [
  { valor: 'academia', nome: 'Academia' },
  { valor: 'leitura', nome: 'Leitura' },
  { valor: 'trabalho', nome: 'Trabalho' },
  { valor: 'aula', nome: 'Faculdade / aula' },
  { valor: 'plantao', nome: 'Plantão' },
  { valor: 'outro', nome: 'Outro' },
];

export const DIAS_CURTOS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'];

/** O que o formulário abre preenchido. Sem isto, abre vazio para adicionar. */
export interface FormInicial {
  input: SeriesInput;
  origem: string | null;
}

@Component({
  selector: 'app-commitment-form',
  templateUrl: './commitment-form.html',
  styleUrl: './commitment-form.scss',
})
export class CommitmentForm implements OnInit {
  readonly inicial = input<FormInicial | null>(null);
  readonly salvando = input(false);
  readonly online = input(true);

  readonly salvar = output<SeriesInput>();
  readonly apagar = output<void>();
  readonly cancelar = output<void>();

  protected readonly tipos = TIPOS;
  protected readonly dias = DIAS_CURTOS;

  protected readonly tipo = signal<CommitmentKind>('academia');
  protected readonly nome = signal('');
  protected readonly modo = signal<'semana' | 'unica'>('semana');
  protected readonly diasMarcados = signal<number[]>([]);
  protected readonly data = signal('');
  protected readonly inicio = signal('');
  protected readonly duracao = signal(60);
  protected readonly vigenciaDe = signal('');
  protected readonly vigenciaAte = signal('');

  /** Hora de fim, derivada de início + duração (passa da meia-noite se preciso). */
  protected readonly fim = computed(() => {
    const inicio = this.inicio();
    if (!inicio) return '';
    const [h, m] = inicio.split(':').map(Number);
    const total = (h * 60 + m + this.duracao()) % (24 * 60);
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  });

  protected readonly editando = computed(() => this.inicial() !== null);
  protected readonly valido = computed(() => {
    const quando = this.modo() === 'semana' ? this.diasMarcados().length > 0 : !!this.data();
    return quando && this.duracao() >= 1 && this.duracao() <= 1440;
  });
  protected readonly podeSalvar = computed(
    () => this.valido() && this.online() && !this.salvando(),
  );

  ngOnInit(): void {
    const inicial = this.inicial()?.input;
    if (!inicial) return;
    this.tipo.set(inicial.kind);
    this.nome.set(inicial.label);
    this.modo.set(inicial.on_day ? 'unica' : 'semana');
    this.diasMarcados.set([...inicial.weekdays].sort());
    this.data.set(inicial.on_day ?? '');
    this.inicio.set(inicial.starts_at ?? '');
    this.duracao.set(inicial.duration_minutes);
    this.vigenciaDe.set(inicial.starts_on ?? '');
    this.vigenciaAte.set(inicial.ends_on ?? '');
  }

  protected valor(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  /** Digitar a hora de fim recalcula a duração; fim antes do início = passa da meia-noite. */
  protected mudarFim(valor: string): void {
    const inicio = this.inicio();
    if (!inicio || !valor) return;
    const [hi, mi] = inicio.split(':').map(Number);
    const [hf, mf] = valor.split(':').map(Number);
    let duracao = hf * 60 + mf - (hi * 60 + mi);
    if (duracao <= 0) duracao += 24 * 60;
    this.duracao.set(duracao);
  }

  protected alternarDia(indice: number): void {
    this.diasMarcados.update((atual) =>
      atual.includes(indice) ? atual.filter((d) => d !== indice) : [...atual, indice].sort(),
    );
  }

  protected enviar(evento: Event): void {
    evento.preventDefault();
    if (!this.podeSalvar()) return;
    const semanal = this.modo() === 'semana';
    this.salvar.emit({
      kind: this.tipo(),
      label: this.nome().trim(),
      weekdays: semanal ? this.diasMarcados() : [],
      on_day: semanal ? null : this.data(),
      starts_at: this.inicio() || null,
      duration_minutes: this.duracao(),
      starts_on: semanal ? this.vigenciaDe() || null : null,
      ends_on: semanal ? this.vigenciaAte() || null : null,
    });
  }
}
