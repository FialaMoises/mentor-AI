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
    expect(rodapes[1]).toBe('estudo: 0');
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
    req.flush({ series_id: null, replan_summary: '12 tarefas replanejadas até 22/11.' });
    http.expectOne((r) => r.url === '/api/v1/me/routine').flush(semana());
    fixture.detectChanges();

    expect(el().textContent).toContain('12 tarefas replanejadas até 22/11.');
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

    expect(el().textContent).toContain('compromisso de um dia só precisa ser de amanhã em diante');
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
});
