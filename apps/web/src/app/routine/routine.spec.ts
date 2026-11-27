import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { RoutineItem, RoutineWeek } from '../core/routine-api';
import { Routine } from './routine';

function item(mudancas: Partial<RoutineItem>): RoutineItem {
  return {
    series_id: 's-academia',
    kind: 'academia',
    label: 'Musculação',
    starts_at: '18:00',
    duration_minutes: 75,
    recurring: true,
    document_name: null,
    edited_by_student: false,
    editable: true,
    ends_on: null,
    series: {
      kind: 'academia',
      label: 'Musculação',
      weekdays: [0, 2, 4],
      on_day: null,
      starts_at: '18:00',
      duration_minutes: 75,
      starts_on: null,
      ends_on: null,
    },
    ...mudancas,
  };
}

function semana(): RoutineWeek {
  const academia = item({});
  const plantao = item({
    series_id: 's-plantao',
    kind: 'plantao',
    label: 'Plantão — PS adulto',
    starts_at: '19:00',
    duration_minutes: 720,
    recurring: false,
    document_name: 'escala.xlsx',
    series: {
      kind: 'plantao',
      label: 'Plantão — PS adulto',
      weekdays: [],
      on_day: '2026-10-04',
      starts_at: '19:00',
      duration_minutes: 720,
      starts_on: null,
      ends_on: null,
    },
  });
  const leitura = item({
    series_id: 's-leitura',
    kind: 'leitura',
    label: 'Leitura',
    starts_at: '22:00',
    duration_minutes: 30,
    series: {
      kind: 'leitura',
      label: 'Leitura',
      weekdays: [3],
      on_day: null,
      starts_at: '22:00',
      duration_minutes: 30,
      starts_on: null,
      ends_on: null,
    },
  });
  const dias = ['28', '29', '30']
    .map((d) => `2026-09-${d}`)
    .concat(['01', '02', '03', '04'].map((d) => `2026-10-${d}`));
  const livres = [120, 0, 120, 120, 120, 120, 0];
  const itens: RoutineItem[][] = [[academia], [], [academia], [leitura], [academia], [], [plantao]];
  return {
    week_start: '2026-09-28',
    today: '2026-09-28',
    changed_today: false,
    days: dias.map((day, i) => ({
      day,
      free_minutes: livres[i],
      light: i === 5,
      computed: false,
      items: itens[i],
    })),
  };
}

describe('Routine', () => {
  let fixture: ComponentFixture<Routine>;
  let http: HttpTestingController;

  function montar(dados: RoutineWeek = semana()): void {
    fixture = TestBed.createComponent(Routine);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(dados);
    fixture.detectChanges();
  }

  function el(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function digitar(seletor: string, valor: string): void {
    const campo = el().querySelector(seletor) as HTMLInputElement;
    campo.value = valor;
    campo.dispatchEvent(new Event('input'));
    campo.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function marcarDia(indice: number): void {
    const caixa = el().querySelectorAll('input.dia-semana')[indice] as HTMLInputElement;
    caixa.click();
    fixture.detectChanges();
  }

  function clicar(seletor: string): void {
    (el().querySelector(seletor) as HTMLElement).click();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Routine],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
  });

  afterEach(() => http.verify());

  it('mostra as sete colunas com os blocos da API', () => {
    montar();

    expect(el().querySelectorAll('.dia').length).toBe(7);
    expect(el().querySelectorAll('.bloco.academia').length).toBe(3);
  });

  it('o rodapé mostra estudo, zero e dia leve', () => {
    montar();

    const rodapes = Array.from(el().querySelectorAll('.rodape')).map((r) => r.textContent?.trim());
    expect(rodapes[0]).toBe('estudo: 2h');
    expect(rodapes[1]).toBe('estudo: 0h');
    expect(rodapes[5]).toBe('dia leve');
  });

  it('plantão noturno de domingo não vaza para fora da semana', () => {
    montar();

    const domingo = el().querySelectorAll('.dia')[6];
    expect(domingo.querySelector('.bloco.plantao')).not.toBeNull();
    expect(el().querySelector('.continua')).toBeNull();
  });

  it('plantão noturno de sábado continua no domingo', () => {
    const dados = semana();
    dados.days[5].items = [dados.days[6].items[0]];
    dados.days[6].items = [];
    montar(dados);

    const domingo = el().querySelectorAll('.dia')[6];
    expect(domingo.querySelector('.continua.plantao')).not.toBeNull();
  });

  it('adicionar academia seg/qua/sex envia a série', () => {
    montar();
    clicar('button.adicionar');
    digitar('input.nome', 'Musculação');
    marcarDia(0);
    marcarDia(2);
    marcarDia(4);
    digitar('input.inicio', '07:00');
    digitar('input.duracao', '60');
    clicar('button.salvar');

    const req = http.expectOne('/api/v1/me/commitment-series');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(
      jasmine.objectContaining({
        kind: 'academia',
        label: 'Musculação',
        weekdays: [0, 2, 4],
        on_day: null,
        starts_at: '07:00',
        duration_minutes: 60,
      }),
    );
    req.flush({ series_id: 's1', replan_summary: '' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('tocar num bloco abre a edição e salvar faz PATCH na série', () => {
    montar();
    clicar('.bloco.academia');

    expect((el().querySelector('input.nome') as HTMLInputElement).value).toBe('Musculação');
    const marcados = Array.from(el().querySelectorAll('input.dia-semana')).map(
      (c) => (c as HTMLInputElement).checked,
    );
    expect(marcados).toEqual([true, false, true, false, true, false, false]);

    digitar('input.inicio', '07:30');
    clicar('button.salvar');

    const req = http.expectOne('/api/v1/me/commitment-series/s-academia');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body.starts_at).toBe('07:30');
    expect(req.request.body.weekdays).toEqual([0, 2, 4]);
    req.flush({ series_id: 's-academia', replan_summary: '' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('bloco de arquivo mostra de onde veio', () => {
    montar();
    clicar('.bloco.plantao');

    expect(el().textContent).toContain('veio de: escala.xlsx');
  });

  it('salvar fica desabilitado enquanto a requisição está aberta', () => {
    montar();
    clicar('.bloco.academia');
    clicar('button.salvar');
    clicar('button.salvar');

    const reqs = http.match('/api/v1/me/commitment-series/s-academia');
    expect(reqs.length).toBe(1);
    expect((el().querySelector('button.salvar') as HTMLButtonElement).disabled).toBeTrue();
    reqs[0].flush({ series_id: 's-academia', replan_summary: '' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('sem rede o salvar fica desabilitado', () => {
    spyOnProperty(navigator, 'onLine').and.returnValue(false);
    montar();
    clicar('button.adicionar');

    expect((el().querySelector('button.salvar') as HTMLButtonElement).disabled).toBeTrue();
    expect(el().textContent).toContain('Sem conexão');
  });

  it('depois de salvar mostra o resumo e recarrega a semana', () => {
    montar();
    clicar('.bloco.academia');
    clicar('button.apagar');

    const req = http.expectOne('/api/v1/me/commitment-series/s-academia');
    expect(req.request.method).toBe('DELETE');
    req.flush({ series_id: null, replan_summary: 'Plano refeito de amanhã até 22/11.' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
    fixture.detectChanges();

    expect(el().textContent).toContain('Plano refeito de amanhã até 22/11.');
    expect(el().querySelector('input.nome')).toBeNull();
  });

  it('semana seguinte pede a API com a segunda certa', () => {
    montar();
    clicar('button.proxima');

    const req = http.expectOne((r) => r.url === '/api/v1/me/routine');
    expect(req.request.params.get('week')).toBe('2026-10-05');
    req.flush(semana());
  });

  it('a edição usa a série vigente, não os dias da semana exibida', () => {
    const dados = semana();
    const rodizio = item({
      series_id: 's-rodizio',
      kind: 'aula',
      label: 'Pediatria',
      starts_at: '07:00',
      duration_minutes: 360,
      series: {
        kind: 'aula',
        label: 'Pediatria',
        weekdays: [0, 1, 2, 3, 4],
        on_day: null,
        starts_at: '07:00',
        duration_minutes: 360,
        starts_on: '2026-09-30',
        ends_on: '2026-12-18',
      },
    });
    dados.days[2].items = [rodizio];
    montar(dados);
    clicar('.bloco.aula');
    digitar('input.inicio', '08:00');
    clicar('button.salvar');

    const req = http.expectOne('/api/v1/me/commitment-series/s-rodizio');
    expect(req.request.body).toEqual(
      jasmine.objectContaining({
        weekdays: [0, 1, 2, 3, 4],
        starts_at: '08:00',
        starts_on: '2026-09-30',
        ends_on: '2026-12-18',
      }),
    );
    req.flush({ series_id: 's-rodizio', replan_summary: '' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('bloco de versão já encerrada abre o que vale de amanhã em diante', () => {
    const dados = semana();
    dados.days[0].items = [
      item({ starts_at: '18:00', series: { ...item({}).series!, starts_at: '19:00' } }),
    ];
    montar(dados);
    clicar('.bloco.academia');

    expect((el().querySelector('input.inicio') as HTMLInputElement).value).toBe('19:00');
  });

  it('tocar em outro bloco com o formulário aberto troca os campos', () => {
    montar();
    clicar('.bloco.academia');
    clicar('.bloco.leitura');

    expect((el().querySelector('input.nome') as HTMLInputElement).value).toBe('Leitura');
    expect((el().querySelector('input.inicio') as HTMLInputElement).value).toBe('22:00');
    const marcados = Array.from(el().querySelectorAll('input.dia-semana')).map(
      (c) => (c as HTMLInputElement).checked,
    );
    expect(marcados).toEqual([false, false, false, true, false, false, false]);
  });

  it('adicionar com uma edição aberta abre o formulário vazio', () => {
    montar();
    clicar('.bloco.academia');
    clicar('button.adicionar');

    expect((el().querySelector('input.nome') as HTMLInputElement).value).toBe('');
  });

  it('série encerrada não abre edição', () => {
    const dados = semana();
    dados.days[0].items = [item({ editable: false, series: null })];
    montar(dados);
    clicar('.bloco.academia');

    expect(el().querySelector('input.nome')).toBeNull();
  });

  it('mostra a mensagem que o servidor devolveu ao recusar', () => {
    montar();
    clicar('.bloco.academia');
    clicar('button.salvar');

    http
      .expectOne('/api/v1/me/commitment-series/s-academia')
      .flush(
        { detail: 'compromisso de um dia só precisa ser de amanhã em diante' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );
    fixture.detectChanges();

    expect(el().textContent).toContain('Compromisso de um dia só precisa ser de amanhã em diante.');
  });

  it('hora de fim calcula a duração, inclusive passando da meia-noite', () => {
    montar();
    clicar('button.adicionar');
    digitar('input.nome', 'Plantão');
    marcarDia(5);
    digitar('input.inicio', '19:00');
    digitar('input.fim', '07:00');

    expect((el().querySelector('input.duracao') as HTMLInputElement).value).toBe('720');
    clicar('button.salvar');
    const req = http.expectOne('/api/v1/me/commitment-series');
    expect(req.request.body.duration_minutes).toBe(720);
    req.flush({ series_id: 's1', replan_summary: '' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('a hora de fim acompanha início e duração', () => {
    montar();
    clicar('.bloco.academia');

    expect((el().querySelector('input.fim') as HTMLInputElement).value).toBe('19:15');
    digitar('input.duracao', '90');
    expect((el().querySelector('input.fim') as HTMLInputElement).value).toBe('19:30');
  });

  it('compromissos que se sobrepõem dividem a coluna e os dois continuam clicáveis', () => {
    const dados = semana();
    dados.days[0].items = [
      item({ series_id: 's-a', label: 'Enfermaria', starts_at: '07:00', duration_minutes: 360 }),
      item({ series_id: 's-b', label: 'Ambulatório', starts_at: '12:00', duration_minutes: 120 }),
    ];
    montar(dados);

    const blocos = Array.from(
      el().querySelectorAll('.dia')[0].querySelectorAll('.linha-do-tempo .bloco'),
    ) as HTMLElement[];
    expect(blocos.length).toBe(2);
    expect(blocos[0].style.left).not.toBe(blocos[1].style.left);
    expect(blocos[0].style.width).toContain('50%');

    blocos[1].click();
    fixture.detectChanges();
    expect((el().querySelector('input.nome') as HTMLInputElement).value).toBe('Musculação');
  });

  it('o pedaço depois da meia-noite também abre a edição', () => {
    // Plantão noturno de sábado: o pedaço de domingo é o "continua".
    const dados = semana();
    dados.days[5].items = [
      item({ series_id: 's-noite', kind: 'plantao', starts_at: '19:00', duration_minutes: 720 }),
    ];
    montar(dados);

    const continua = el().querySelector('.continua') as HTMLButtonElement;
    expect(continua.tagName).toBe('BUTTON');
    continua.click();
    fixture.detectChanges();
    expect(el().querySelector('.formulario')).toBeTruthy();
  });

  it('Esc fecha o formulário e o foco volta para o + adicionar', async () => {
    montar();
    const adicionar = el().querySelector('button.adicionar') as HTMLButtonElement;
    adicionar.focus();
    adicionar.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(el().querySelector('.formulario')?.contains(document.activeElement)).toBeTrue();

    const formulario = el().querySelector('.formulario') as HTMLElement;
    formulario.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(el().querySelector('.formulario')).toBeNull();
    expect(document.activeElement).toBe(el().querySelector('button.adicionar'));
  });

  it('datas do formulário começam amanhã', () => {
    montar();
    clicar('button.adicionar');
    (el().querySelector('details.mais') as HTMLDetailsElement).open = true;
    fixture.detectChanges();

    expect((el().querySelector('input.vigencia-de') as HTMLInputElement).min).toBe('2026-09-29');
    clicar('input[value=unica]');
    expect((el().querySelector('input.data') as HTMLInputElement).min).toBe('2026-09-29');
  });

  it('bloco que não dá para editar explica por quê', () => {
    const dados = semana();
    dados.days[0].items = [item({ editable: false, series: null })];
    montar(dados);
    clicar('.bloco.academia');

    expect(el().querySelector('.resumo')?.textContent).toContain('não dá para mudar');
  });

  it('dois cliques rápidos em próxima andam duas semanas e a resposta velha é descartada', () => {
    montar();
    clicar('button.proxima');
    clicar('button.proxima');

    const pedidos = http.match((r) => r.url === '/api/v1/me/routine');
    expect(pedidos.length).toBe(2);
    expect(pedidos[0].cancelled).toBeTrue();
    expect(pedidos[1].request.params.get('week')).toBe('2026-10-12');
    const daqui2 = semana();
    daqui2.week_start = '2026-10-12';
    pedidos[1].flush(daqui2);
    fixture.detectChanges();

    expect(el().querySelector('.periodo')?.textContent).toContain('12/10');
  });

  it('as abas dizem qual dia está aberto', () => {
    montar();

    const abas = Array.from(el().querySelectorAll('.aba')) as HTMLElement[];
    expect(abas[0].getAttribute('aria-pressed')).toBe('true');
    expect(abas[1].getAttribute('aria-pressed')).toBe('false');
  });

  it('o nome do dia é um h2 e o chip sem horário tem o nome inteiro no title', () => {
    const dados = semana();
    dados.days[1].items = [item({ starts_at: null, label: 'Musculação com o personal' })];
    montar(dados);

    expect(el().querySelector('h2.dia-nome')).toBeTruthy();
    const chip = el().querySelector('.chip') as HTMLElement;
    expect(chip.getAttribute('title')).toContain('Musculação com o personal');
  });

  it('depois de um erro ao carregar a semana, próxima ainda carrega', () => {
    montar();
    clicar('button.proxima');
    http
      .expectOne((r) => r.url === '/api/v1/me/routine')
      .error(new ProgressEvent('error'), { status: 0 });
    fixture.detectChanges();
    expect(el().querySelector('.alert')?.textContent).toContain('Sem conexão');

    clicar('button.proxima');
    const req = http.expectOne((r) => r.url === '/api/v1/me/routine');
    expect(req.request.params.get('week')).toBe('2026-10-05');
    const seguinte = semana();
    seguinte.week_start = '2026-10-05';
    req.flush(seguinte);
    fixture.detectChanges();

    expect(el().querySelector('.periodo')?.textContent).toContain('05/10');
    expect(el().querySelector('.alert')).toBeNull();
  });

  it('salvar depois de um erro de carregamento recarrega a semana', () => {
    montar();
    clicar('button.proxima');
    http
      .expectOne((r) => r.url === '/api/v1/me/routine')
      .flush({}, { status: 500, statusText: 'erro' });
    fixture.detectChanges();

    clicar('.bloco.academia');
    clicar('button.salvar');
    http
      .expectOne('/api/v1/me/commitment-series/s-academia')
      .flush({ series_id: 's-academia', replan_summary: 'ok' });

    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
  });

  it('a faixa sem horário tem a mesma altura na coluna de horas e na do dia', () => {
    const dados = semana();
    dados.days[0].items = [
      item({ starts_at: null, label: 'Leitura livre' }),
      ...dados.days[0].items,
    ];
    montar(dados);

    const horas = el().querySelector('.horas .sem-horario') as HTMLElement;
    const dia = el().querySelector('.dia .sem-horario') as HTMLElement;
    expect(horas.style.getPropertyValue('--chips')).toBe('1');
    expect(horas.getBoundingClientRect().height).toBe(dia.getBoundingClientRect().height);
  });
});
