import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { DayPlan } from '../core/models';
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

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Today],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(Today);
    http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('mostra as tarefas do dia devolvidas pela API', () => {
    http
      .expectOne((r) => r.url.endsWith('/plan/today'))
      .flush(plano);
    fixture.detectChanges();

    const topicos = fixture.nativeElement.querySelectorAll('.topic');
    expect(topicos.length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('0 de 2');
  });

  it('marca feito na hora e envia o progresso', () => {
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    fixture.detectChanges();

    const botao = fixture.nativeElement.querySelector('.task button') as HTMLButtonElement;
    botao.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('1 de 2');
    const req = http.expectOne('/api/v1/tasks/t1/progress');
    expect(req.request.body).toEqual({ action: 'feita' });
    req.flush({ ...plano.tasks[0], status: 'feita' });
  });

  it('desfaz a marcação quando a API falha', () => {
    http.expectOne((r) => r.url.endsWith('/plan/today')).flush(plano);
    fixture.detectChanges();

    const botao = fixture.nativeElement.querySelector('.task button') as HTMLButtonElement;
    botao.click();
    fixture.detectChanges();

    http
      .expectOne('/api/v1/tasks/t1/progress')
      .flush({}, { status: 500, statusText: 'erro' });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('0 de 2');
    expect(fixture.nativeElement.querySelector('.alert')).toBeTruthy();
  });
});
