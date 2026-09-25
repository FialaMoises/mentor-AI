import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DayPlan } from '../core/models';
import { OfflineQueue } from '../core/offline-queue';
import { Today } from './today';

const plano: DayPlan = {
  date: '2026-09-24',
  capacity_minutes: 120,
  light: false,
  plan_version: 1,
  tasks: [
    { id: 't1', kind: 'teoria', topic: 'Insuficiência cardíaca', minutes: 60, status: 'pendente' },
    { id: 't2', kind: 'questoes', topic: 'Insuficiência cardíaca', minutes: 60, status: 'pendente' },
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
});
