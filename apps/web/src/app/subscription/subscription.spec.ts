import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AssinaturaOut } from '../core/auth-api';
import { OfflineQueue } from '../core/offline-queue';
import { Session } from '../core/session';
import { SubscriptionPage } from './subscription';

const TRIAL: AssinaturaOut = {
  status: 'trial',
  plan: 'mensal',
  price_cents: 4900,
  trial_ends_on: '2026-12-11',
  current_period_end: null,
  paused_until: null,
  has_access: true,
  price_monthly_cents: 4900,
  price_annual_cents: 47000,
};

describe('SubscriptionPage', () => {
  let fixture: ComponentFixture<SubscriptionPage>;
  let http: HttpTestingController;
  let el: HTMLElement;
  let navegar: jasmine.Spy;

  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [SubscriptionPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    TestBed.inject(Session).abrir('token');
    navegar = spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
    fixture = TestBed.createComponent(SubscriptionPage);
    http = TestBed.inject(HttpTestingController);
    el = fixture.nativeElement;
    fixture.detectChanges();
    http.expectOne('/api/v1/me/subscription').flush(TRIAL);
    fixture.detectChanges();
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  function botao(texto: string): HTMLButtonElement {
    const achado = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent?.includes(texto),
    );
    if (!achado) throw new Error(`sem botão "${texto}"`);
    return achado;
  }

  it('apagar a conta pede confirmação antes de mandar o DELETE', () => {
    botao('Apagar minha conta').click();
    fixture.detectChanges();

    http.expectNone('/api/v1/me');
    expect(el.textContent).toContain('Apagar para sempre');
  });

  it('desistir da exclusão não apaga nada', () => {
    botao('Apagar minha conta').click();
    fixture.detectChanges();
    botao('Não apagar').click();
    fixture.detectChanges();

    http.expectNone('/api/v1/me');
    expect(el.textContent).not.toContain('Apagar para sempre');
  });

  it('confirmada, a exclusão apaga a conta, limpa a fila offline e vai para /entrar', () => {
    TestBed.inject(OfflineQueue).enfileirar({ task_id: 't1', action: 'feita' });
    botao('Apagar minha conta').click();
    fixture.detectChanges();

    botao('Apagar para sempre').click();
    http.expectOne((r) => r.method === 'DELETE' && r.url === '/api/v1/me').flush(null);

    expect(TestBed.inject(OfflineQueue).todas().length).toBe(0);
    expect(TestBed.inject(Session).token).toBeNull();
    expect(navegar).toHaveBeenCalledWith(['/entrar']);
  });

  it('sair com marcações pendentes tenta subir a fila antes', () => {
    TestBed.inject(OfflineQueue).enfileirar({ task_id: 't1', action: 'feita' });

    botao('Sair').click();
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ applied: 1, duplicates: 0, unknown: 0, rejected: 0 });
    http.expectOne('/api/v1/auth/logout').flush(null);

    expect(navegar).toHaveBeenCalledWith(['/entrar']);
  });

  it('sem rede para subir a fila, sair avisa quantas marcações se perdem e pede confirmação', () => {
    TestBed.inject(OfflineQueue).enfileirar({ task_id: 't1', action: 'feita' });

    botao('Sair').click();
    http.expectOne('/api/v1/me/progress/sync').error(new ProgressEvent('error'), { status: 0 });
    fixture.detectChanges();

    http.expectNone('/api/v1/auth/logout');
    expect(el.textContent).toContain('1 marcação');
    botao('Sair mesmo assim').click();
    http.expectOne('/api/v1/auth/logout').flush(null);
    expect(TestBed.inject(OfflineQueue).todas().length).toBe(0);
  });

  it('a pausa mostra o motivo que o servidor deu, e o sucesso apaga o erro', () => {
    const componente = fixture.componentInstance as unknown as { pausarAte: string };
    componente.pausarAte = '2026-12-20';
    botao('Pausar').click();
    http
      .expectOne('/api/v1/me/subscription/pause')
      .flush({ detail: 'assinatura cancelada não pausa' }, { status: 422, statusText: 'erro' });
    fixture.detectChanges();
    expect(el.querySelector('.alert')?.textContent).toContain('Assinatura cancelada não pausa.');

    botao('Pausar').click();
    http
      .expectOne('/api/v1/me/subscription/pause')
      .flush({ ...TRIAL, status: 'pausada', paused_until: '2026-12-20' });
    fixture.detectChanges();
    expect(el.querySelector('.alert')).toBeNull();
  });

  it('só segue um checkout https', () => {
    const componente = fixture.componentInstance as unknown as {
      urlDeCheckoutSegura(url: string): boolean;
    };

    expect(componente.urlDeCheckoutSegura('https://pagamento.exemplo/x')).toBeTrue();
    expect(componente.urlDeCheckoutSegura('javascript:alert(1)')).toBeFalse();
    expect(componente.urlDeCheckoutSegura('http://pagamento.exemplo/x')).toBeFalse();
  });

  it('cancelar não promete perda de acesso: a cobrança para e o plano continua', () => {
    botao('Cancelar assinatura').click();
    fixture.detectChanges();

    const texto = el.textContent ?? '';
    expect(texto).not.toContain('e o acesso');
    expect(texto).toContain('Cancelar encerra a cobrança');
    expect(texto).toContain('O plano e os seus dados continuam disponíveis');
  });

  it('pausada ou sem acesso, a tela diz que o plano e os dados continuam disponíveis', () => {
    fixture.componentInstance['assinatura'].set({
      ...TRIAL,
      status: 'pausada',
      paused_until: '2026-12-20',
      has_access: false,
    });
    fixture.detectChanges();

    const texto = el.textContent ?? '';
    expect(texto).toContain('continuam disponíveis');
    expect(texto).not.toContain('plano está parado');
    expect(texto).not.toContain('Voltar a estudar');
  });

  it('status, data e preço aparecem em português', () => {
    const texto = el.textContent ?? '';

    expect(texto).toContain('Período de teste');
    expect(texto).toContain('11/12/2026');
    expect(texto).not.toContain('2026-12-11');
    expect(texto).toMatch(/R\$\s?49,00/);
  });

  it('no teste, os botões de assinar já mostram o preço de cada plano', () => {
    expect(botao('Mensal').textContent).toMatch(/R\$\s?49,00/);
    expect(botao('Anual').textContent).toMatch(/R\$\s?470,00/);
  });

  it('pausada, a frase da cobrança parada aparece uma vez só', () => {
    fixture.componentInstance['assinatura'].set({
      ...TRIAL,
      status: 'pausada',
      paused_until: '2026-12-20',
      has_access: false,
    });
    fixture.detectChanges();

    const vezes = (el.textContent ?? '').split('A cobrança está parada').length - 1;
    expect(vezes).toBe(1);
  });

  it('sair com a fila subida avisa das marcações que o servidor não aceitou', () => {
    TestBed.inject(OfflineQueue).enfileirar({ task_id: 't1', action: 'feita' });

    botao('Sair').click();
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ applied: 0, duplicates: 0, unknown: 0, rejected: 1 });
    fixture.detectChanges();

    http.expectNone('/api/v1/auth/logout');
    expect(el.textContent).toContain('1 marcação feita sem internet não pôde ser salva');
    botao('Sair mesmo assim').click();
    http.expectOne('/api/v1/auth/logout').flush(null);
  });

  it('sair avisa também da marcação que ficou só no histórico (stale)', () => {
    TestBed.inject(OfflineQueue).enfileirar({ task_id: 't1', action: 'feita' });

    botao('Sair').click();
    http
      .expectOne('/api/v1/me/progress/sync')
      .flush({ applied: 0, duplicates: 0, unknown: 0, rejected: 0, stale: 1 });
    fixture.detectChanges();

    http.expectNone('/api/v1/auth/logout');
    expect(el.textContent).toContain('1 marcação feita sem internet não pôde ser salva');
  });
});
