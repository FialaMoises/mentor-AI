import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { authInterceptor } from '../core/auth-interceptor';
import { hojeIso } from '../core/datas';
import { DayPlan } from '../core/models';
import { OfflineQueue } from '../core/offline-queue';
import { Session } from '../core/session';
import { Today } from './today';

const plano: DayPlan = {
  date: hojeIso(),
  capacity_minutes: 120,
  light: false,
  plan_version: 1,
  tasks: [
    { id: 't1', kind: 'teoria', topic: 'Insuficiência cardíaca', minutes: 60, status: 'pendente' },
    {
      id: 't2',
      kind: 'questoes',
      topic: 'Insuficiência cardíaca',
      minutes: 60,
      status: 'pendente',
    },
  ],
};

describe('Today', () => {
  let fixture: ComponentFixture<Today>;
  let http: HttpTestingController;
  let fila: OfflineQueue;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [Today],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(Today);
    http = TestBed.inject(HttpTestingController);
    fila = TestBed.inject(OfflineQueue);
    fixture.detectChanges();
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  function botoes(): HTMLButtonElement[] {
    return Array.from(fixture.nativeElement.querySelectorAll('.task button'));
  }

  it('mostra as tarefas do dia devolvidas pela API', () => {
    expect(fixture.nativeElement.querySelectorAll('.topic').length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('0 de 2');
  });

  it('marca feito na hora e envia com o id da marcação', () => {
    botoes()[0].click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('1 de 2');
    const req = http.expectOne('/api/v1/tasks/t1/progress');
    expect(req.request.body.action).toBe('feita');
    expect(req.request.body.client_event_id).toBeTruthy();
    req.flush({ ...plano.tasks[0], status: 'feita' });

    expect(fila.todas().length).toBe(0);
  });

  it('em questões, o primeiro toque abre o lançamento de acertos', () => {
    const feito = botoes().find((b) => b.textContent?.includes('Feito'));
    // O segundo item é o de questões: pega o "Feito" dele.
    const feitoQuestoes = Array.from(
      fixture.nativeElement.querySelectorAll('.task'),
    )[1] as HTMLElement;
    (feitoQuestoes.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(feito).toBeTruthy();
    expect(fixture.nativeElement.querySelector('.acertos')).toBeTruthy();
    http.expectNone('/api/v1/tasks/t2/progress');
  });

  it('o segundo toque envia quantas acertou', () => {
    const questoes = Array.from(fixture.nativeElement.querySelectorAll('.task'))[1] as HTMLElement;
    (questoes.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();

    const salvar = Array.from(questoes.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Salvar'),
    ) as HTMLButtonElement;
    salvar.click();
    fixture.detectChanges();

    const req = http.expectOne('/api/v1/tasks/t2/progress');
    expect(req.request.body.answered).toBe(20);
    expect(req.request.body.correct).toBe(0);
    req.flush({ ...plano.tasks[1], status: 'feita' });
  });

  it('sem rede, a marcação fica na fila e a tela mantém o feito', () => {
    botoes()[0].click();
    fixture.detectChanges();

    // status 0 é o que o navegador devolve quando não há conexão.
    http.expectOne('/api/v1/tasks/t1/progress').error(new ProgressEvent('error'), { status: 0 });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('1 de 2');
    expect(fila.todas().length).toBe(1);
    expect(fila.todas()[0].task_id).toBe('t1');
  });

  it('erro do servidor desfaz a marcação e esvazia a fila', () => {
    botoes()[0].click();
    fixture.detectChanges();

    http.expectOne('/api/v1/tasks/t1/progress').flush({}, { status: 500, statusText: 'erro' });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('0 de 2');
    expect(fila.todas().length).toBe(0);
    expect(fixture.nativeElement.querySelector('.alert')).toBeTruthy();
  });

  it('acertos acima do total: avisa junto do campo e não deixa salvar', () => {
    const questoes = Array.from(fixture.nativeElement.querySelectorAll('.task'))[1] as HTMLElement;
    (questoes.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();
    const acertos = questoes.querySelector('input[name=acertos]') as HTMLInputElement;
    acertos.value = '25';
    acertos.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const salvar = Array.from(questoes.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Salvar'),
    ) as HTMLButtonElement;
    expect(salvar.disabled).toBeTrue();
    expect(questoes.querySelector('.erro-acertos')?.textContent).toContain('25 acertos de 20');
    salvar.click();
    http.expectNone('/api/v1/tasks/t2/progress');
    expect(fila.todas().length).toBe(0);

    acertos.value = '15';
    acertos.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(salvar.disabled).toBeFalse();
    salvar.click();
    const req = http.expectOne('/api/v1/tasks/t2/progress');
    expect(req.request.body.correct).toBe(15);
    req.flush({ ...plano.tasks[1], status: 'feita' });
  });

  it('a marcação que deu certo apaga o erro antigo da tela', () => {
    botoes()[0].click();
    http.expectOne('/api/v1/tasks/t1/progress').flush({}, { status: 500, statusText: 'erro' });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.alert')).toBeTruthy();

    botoes()[0].click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.alert')).toBeNull();
    http.expectOne('/api/v1/tasks/t1/progress').flush({ ...plano.tasks[0], status: 'feita' });
  });

  it('lista de outro dia (vinda do cache) avisa de que dia ela é', () => {
    fixture.componentInstance['plan'].set({ ...plano, date: '2020-01-02' });
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.aviso-data')?.textContent).toContain('02/01');
  });

  it('o tipo da tarefa aparece em português', () => {
    const tipos = Array.from(fixture.nativeElement.querySelectorAll('.kind')).map((e) =>
      (e as HTMLElement).textContent?.trim(),
    );
    expect(tipos).toEqual(['Teoria', 'Questões']);
  });

  it('os botões dizem de qual tarefa são', () => {
    const feito = botoes()[0];
    expect(feito.getAttribute('aria-label')).toBe('Feito: Insuficiência cardíaca (Teoria)');
  });

  it('tarefa marcada diz em texto se foi feita ou não deu', () => {
    fixture.componentInstance['plan'].set({
      ...plano,
      tasks: [
        { ...plano.tasks[0], status: 'feita' },
        { ...plano.tasks[1], status: 'nao_deu' },
      ],
    });
    fixture.detectChanges();

    const selos = Array.from(fixture.nativeElement.querySelectorAll('.selo')).map((e) =>
      (e as HTMLElement).textContent?.trim(),
    );
    expect(selos).toEqual(['✓ feita', 'não deu']);
  });

  it('primeiro dia (o plano começa depois de hoje) explica que o plano começa amanhã', () => {
    fixture.componentInstance['plan'].set({
      ...plano,
      tasks: [],
      plan_version: 0,
      plan_starts_on: '2999-01-01',
    });
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Seu plano começa');
    expect(texto).not.toContain('min disponíveis');
  });

  it('dia sem tarefa no meio do plano diz só que nada foi planejado', () => {
    fixture.componentInstance['plan'].set({
      ...plano,
      tasks: [],
      plan_version: 0,
      plan_starts_on: '2020-01-01',
    });
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Nada planejado para hoje.');
    expect(texto).not.toContain('Seu plano começa amanhã');
  });

  it('o plano que começa amanhã diz "amanhã"', () => {
    const amanha = new Date();
    amanha.setDate(amanha.getDate() + 1);
    fixture.componentInstance['plan'].set({
      ...plano,
      tasks: [],
      plan_starts_on: hojeIso(amanha),
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Seu plano começa amanhã.');
  });

  it('o plano que começa depois de amanhã diz o dia', () => {
    fixture.componentInstance['plan'].set({
      ...plano,
      date: '2026-11-27',
      tasks: [],
      plan_starts_on: '2026-11-30',
    });
    fixture.detectChanges();

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Seu plano começa seg, 30/11.');
    expect(texto).not.toContain('amanhã.');
  });
});

describe('Today: a fila offline ao voltar a rede', () => {
  let fixture: ComponentFixture<Today>;
  let http: HttpTestingController;
  let fila: OfflineQueue;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [Today],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fila = TestBed.inject(OfflineQueue);
    fila.enfileirar({ task_id: 't1', action: 'feita' });
    fila.enfileirar({ task_id: 'outra', action: 'feita' });
    fixture = TestBed.createComponent(Today);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('marcação mais velha que a última da tarefa sai da fila com aviso', () => {
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ applied: 1, duplicates: 0, unknown: 0, rejected: 0, stale: 1 });
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    fixture.detectChanges();

    expect(fila.todas().length).toBe(0);
    expect(fixture.nativeElement.querySelector('.aviso-fila')?.textContent).toContain('1 marcação');
  });

  it('marcação que o servidor não reconheceu sai da fila com aviso', () => {
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ applied: 1, duplicates: 0, unknown: 1, rejected: 0 });
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    fixture.detectChanges();

    expect(fila.todas().length).toBe(0);
    expect(fixture.nativeElement.querySelector('.aviso-fila')?.textContent).toContain('1 marcação');
  });

  it('erro do servidor (5xx) mantém a fila para tentar de novo', () => {
    http.expectOne('/api/v1/me/progress/sync').flush({}, { status: 500, statusText: 'erro' });

    expect(fila.todas().length).toBe(2);
  });

  it('a fila recusada de vez (4xx) sai do aparelho com aviso, sem travar para sempre', () => {
    http.expectOne('/api/v1/me/progress/sync').flush({}, { status: 422, statusText: 'erro' });
    fixture.detectChanges();

    expect(fila.todas().length).toBe(0);
    expect(fixture.nativeElement.querySelector('.aviso-fila')).toBeTruthy();
  });
});

describe('Today com o interceptor de sessão', () => {
  it('um 401 na subida da fila não apaga as marcações guardadas', async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [Today],
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    }).compileComponents();
    spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    TestBed.inject(Session).abrir('token-velho');
    const fila = TestBed.inject(OfflineQueue);
    fila.enfileirar({ task_id: 't1', action: 'feita' });

    const fixture = TestBed.createComponent(Today);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ detail: 'sessão expirada' }, { status: 401, statusText: 'erro' });

    expect(TestBed.inject(Session).token).toBeNull();
    expect(fila.todas().length).toBe(1);
    http.verify();
    localStorage.clear();
  });
});
