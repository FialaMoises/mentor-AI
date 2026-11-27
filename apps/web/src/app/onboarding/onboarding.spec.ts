import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { amanhaIso } from '../core/datas';
import { DocumentoOut, RotinaExtraida } from '../core/onboarding-api';
import { Onboarding } from './onboarding';

const CATALOGO = {
  exam: 'enamed',
  exam_name: 'ENAMED',
  weights_source: 'uniforme',
  areas: [
    { slug: 'clinica-medica', name: 'Clínica Médica', temas: [] },
    { slug: 'pediatria', name: 'Pediatria', temas: [] },
  ],
};

function eu(needs_onboarding: boolean, consent_required: boolean) {
  return {
    id: 'a1',
    email: 'aluno@exemplo.com',
    phase: 'faculdade',
    mode: 'independente',
    weekly_hours: 14,
    needs_onboarding,
    subscription_status: 'trial',
    trial_ends_on: null,
    consent_required,
    today: '2027-01-10',
  };
}

const ROTINA: RotinaExtraida = {
  commitments: [
    {
      kind: 'aula',
      label: 'Internato',
      weekday: 2,
      on_day: null,
      duration_minutes: 240,
      starts_at: '07:00',
      starts_on: null,
      ends_on: null,
    },
    {
      kind: 'plantao',
      label: 'Plantão extra',
      weekday: null,
      on_day: '2027-01-15',
      duration_minutes: 720,
      starts_at: '19:00',
      starts_on: null,
      ends_on: null,
    },
  ],
  exams: [{ name: 'Prova da faculdade', exam_date: '2027-03-10' }],
  unreadable: [],
};

const DOCUMENTO: DocumentoOut = {
  id: 'd1',
  kind: 'grade',
  original_name: 'grade.pdf',
  status: 'extraido',
  error: '',
  extracted: ROTINA,
  original_kept: true,
  edited_blocks: 0,
};

describe('Onboarding', () => {
  let fixture: ComponentFixture<Onboarding>;
  let http: HttpTestingController;
  let el: HTMLElement;

  async function montar(needs = true, aceitou = true): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [Onboarding],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(Onboarding);
    http = TestBed.inject(HttpTestingController);
    el = fixture.nativeElement;
    fixture.detectChanges();
    http.expectOne('/api/v1/catalog/enamed').flush(CATALOGO);
    http.expectOne('/api/v1/me').flush(eu(needs, !aceitou));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  afterEach(() => http.verify());

  function botao(texto: string): HTMLButtonElement {
    const achado = Array.from(el.querySelectorAll('button')).find((b) =>
      (b.getAttribute('aria-label') ?? b.textContent)?.includes(texto),
    );
    if (!achado) throw new Error(`sem botão "${texto}"`);
    return achado;
  }

  async function chegarNaConferencia(): Promise<void> {
    await montar(false, false);
    // Perfil pronto e sem aceite: começa no aviso; o upload vem depois do aceite.
    botao('Entendi e concordo').click();
    http.expectOne('/api/v1/me/consent').flush({ accepted: true, policy_version: 'x' });
    fixture.detectChanges();
    const arquivo = new File(['%PDF-1.7'], 'grade.pdf', { type: 'application/pdf' });
    const entrada = el.querySelector('input[type=file]') as HTMLInputElement;
    const lista = new DataTransfer();
    lista.items.add(arquivo);
    entrada.files = lista.files;
    entrada.dispatchEvent(new Event('change'));
    http.expectOne('/api/v1/me/documents').flush(DOCUMENTO);
    fixture.detectChanges();
  }

  it('aluno novo: preencher a data da prova habilita o Continuar', async () => {
    await montar(true);
    expect(botao('Continuar').disabled).toBeTrue();

    const data = el.querySelector('input[type=date]') as HTMLInputElement;
    data.value = '2027-09-20';
    data.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(botao('Continuar').disabled).toBeFalse();
  });

  it('a data da prova não aceita hoje nem o passado', async () => {
    await montar(true);

    const data = el.querySelector('input[type=date]') as HTMLInputElement;
    expect(data.min).toBe(amanhaIso());
  });

  it('mostra o motivo que o servidor deu quando recusa o perfil', async () => {
    await montar(true);
    const data = el.querySelector('input[type=date]') as HTMLInputElement;
    data.value = '2027-09-20';
    data.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    botao('Continuar').click();
    http
      .expectOne('/api/v1/me/profile')
      .flush(
        { detail: 'a data da prova principal precisa ser de amanhã em diante' },
        { status: 422, statusText: 'erro' },
      );
    fixture.detectChanges();

    expect(el.querySelector('.alert')?.textContent).toContain(
      'A data da prova principal precisa ser de amanhã em diante.',
    );
  });

  it('quem já tem perfil e ainda não aceitou começa no aviso, sem refazer o questionário', async () => {
    await montar(false, false);
    expect(el.textContent).toContain('Seus arquivos');
    expect(el.textContent).not.toContain('Vamos montar seu plano');
  });

  it('quem já aceitou o aviso vai direto para o upload', async () => {
    await montar(false, true);

    expect(el.querySelector('input[type=file]')).toBeTruthy();
    expect(el.textContent).not.toContain('Vamos montar seu plano');
  });

  it('dá para seguir sem arquivo: replaneja e vai para /hoje', async () => {
    await montar(false, true);
    const router = TestBed.inject(Router);
    const navegar = spyOn(router, 'navigate').and.resolveTo(true);

    botao('Seguir sem arquivo').click();
    http.expectOne('/api/v1/me/plan/replan').flush({ plan_version: 1, summary: 'ok' });

    expect(navegar).toHaveBeenCalledWith(['/hoje']);
  });

  it('na conferência, cada compromisso mostra o dia que foi lido', async () => {
    await chegarNaConferencia();

    const select = el.querySelector('.compromissos select') as HTMLSelectElement;
    expect(select.value).toBe('2');
    expect(select.selectedOptions[0].textContent).toContain('Quarta');
  });

  it('compromisso de data única mostra a data, não um dia da semana', async () => {
    await chegarNaConferencia();

    const itens = el.querySelectorAll('.compromissos li');
    const dataUnica = itens[1] as HTMLElement;
    expect(dataUnica.querySelector('select')).toBeNull();
    expect((dataUnica.querySelector('input[type=date]') as HTMLInputElement).value).toBe(
      '2027-01-15',
    );
  });

  it('duração vazia não vira zero: o confirmar fica parado e a tela diz o que falta', async () => {
    await chegarNaConferencia();

    const duracao = el.querySelector('.compromissos input[type=number]') as HTMLInputElement;
    expect(duracao.min).toBe('1');
    duracao.value = '';
    duracao.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(botao('Está certo').disabled).toBeTrue();
    expect(el.textContent).toContain('Confira a duração de Internato');
  });

  it('a prova lida do arquivo aparece na conferência e pode sair', async () => {
    await chegarNaConferencia();
    expect(el.textContent).toContain('Prova da faculdade');

    botao('remover a prova Prova da faculdade').click();
    fixture.detectChanges();
    botao('Está certo').click();

    const req = http.expectOne('/api/v1/documents/d1/confirm');
    expect(req.request.body.exams).toEqual([]);
    req.flush({ document: DOCUMENTO, commitments: 2, days_recalculated: 1, replan_summary: 'ok' });
  });

  it('clique duplo em confirmar manda um pedido só', async () => {
    await chegarNaConferencia();

    const confirmar = botao('Está certo');
    confirmar.click();
    confirmar.click();

    const pedidos = http.match('/api/v1/documents/d1/confirm');
    expect(pedidos.length).toBe(1);
    pedidos[0].flush({
      document: DOCUMENTO,
      commitments: 2,
      days_recalculated: 1,
      replan_summary: 'Plano refeito.',
    });
  });

  it('na conferência, o que o confirm vai descartar aparece como "já passou, não entra"', async () => {
    // Hoje (do servidor) é 10/01/2027: o plantão de 15/01 vale, a prova de 10/03 também.
    await chegarNaConferencia();
    const componente = fixture.componentInstance as unknown as {
      rotina: { set(v: unknown): void };
    };
    componente.rotina.set({
      ...ROTINA,
      commitments: [
        ROTINA.commitments[0],
        { ...ROTINA.commitments[1], on_day: '2027-01-05' },
        { ...ROTINA.commitments[0], label: 'Rodízio antigo', ends_on: '2027-01-02' },
      ],
      exams: [{ name: 'Prova velha', exam_date: '2026-12-01' }],
    });
    fixture.detectChanges();

    const passados = Array.from(el.querySelectorAll('.passou')).map((e) => e.textContent);
    expect(passados.length).toBe(3);
    expect(passados.every((t) => t?.includes('já passou, não entra'))).toBeTrue();
    expect(el.textContent).not.toContain('Nada deste arquivo vale de hoje em diante');
  });

  it('quando nada do arquivo vale de hoje em diante, avisa antes e não diz "Plano pronto"', async () => {
    await chegarNaConferencia();
    const componente = fixture.componentInstance as unknown as {
      rotina: { set(v: unknown): void };
    };
    componente.rotina.set({
      ...ROTINA,
      commitments: [{ ...ROTINA.commitments[1], on_day: '2027-01-05' }],
      exams: [],
    });
    fixture.detectChanges();
    expect(el.textContent).toContain('Nada deste arquivo vale de hoje em diante');

    botao('Está certo').click();
    http
      .expectOne('/api/v1/documents/d1/confirm')
      .flush({ document: DOCUMENTO, commitments: 1, days_recalculated: 1, replan_summary: 'x' });
    fixture.detectChanges();

    expect(el.querySelector('h1')?.textContent).not.toContain('Plano pronto');
  });

  it('a data única da conferência aceita hoje, como o servidor', async () => {
    await chegarNaConferencia();

    const data = el.querySelector(
      '.compromissos li:nth-child(2) input[type=date]',
    ) as HTMLInputElement;
    expect(data.min).toBe('2027-01-10');
  });

  it('os botões remover dizem tipo, rótulo e dia', async () => {
    await chegarNaConferencia();

    const rotulos = Array.from(el.querySelectorAll('.compromissos button')).map((b) =>
      b.getAttribute('aria-label'),
    );
    expect(rotulos).toContain('remover aula Internato, Quarta');
    expect(rotulos).toContain('remover plantão Plantão extra, 15/01/2027');
  });

  it('quem veio da rotina tem como voltar para ela', async () => {
    await montar(false, true);

    const voltar = el.querySelector('a.voltar') as HTMLAnchorElement;
    expect(voltar.textContent).toContain('Voltar para Minha rotina');
    expect(voltar.getAttribute('href')).toBe('/rotina');
  });

  it('aluno novo não vê o voltar', async () => {
    await montar(true);

    expect(el.querySelector('a.voltar')).toBeNull();
  });
});
