import { registerLocaleData } from '@angular/common';
import localePt from '@angular/common/locales/pt';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { LOCALE_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { App } from './app';
import { appConfig } from './app.config';
import { routes } from './app.routes';
import { Session } from './core/session';

describe('App', () => {
  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  afterEach(() => localStorage.clear());

  it('monta a casca com a marca', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const brand = fixture.nativeElement.querySelector('.brand') as HTMLElement;
    expect(brand.textContent).toContain('mentor-AI');
  });

  it('tem um atalho para pular direto ao conteúdo', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const pular = fixture.nativeElement.querySelector('a.pular') as HTMLAnchorElement;
    expect(pular.getAttribute('href')).toBe('#conteudo');
    expect(fixture.nativeElement.querySelector('main#conteudo')).toBeTruthy();
  });

  it('o menu marca a página atual para o leitor de tela', async () => {
    TestBed.inject(Session).abrir('abc');
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/conta');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const atual = fixture.nativeElement.querySelector('nav a[aria-current="page"]');
    expect(atual?.textContent).toContain('Conta');
  });

  it('o menu do aluno some no painel de admin', async () => {
    TestBed.inject(Session).abrir('abc');
    const fixture = TestBed.createComponent(App);
    await TestBed.inject(Router).navigateByUrl('/admin');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('nav')).toBeNull();
  });

  it('toda rota tem título próprio', () => {
    const semTitulo = routes.filter((r) => r.loadComponent && !r.title).map((r) => r.path);
    expect(semTitulo).toEqual([]);
  });

  it('números e datas saem em pt-BR', () => {
    const locale = appConfig.providers.find(
      (p) => typeof p === 'object' && p !== null && 'provide' in p && p.provide === LOCALE_ID,
    ) as { useValue: string } | undefined;
    registerLocaleData(localePt);
    expect(locale?.useValue).toBe('pt-BR');
  });
});
