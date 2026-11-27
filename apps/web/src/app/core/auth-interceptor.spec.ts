import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { authInterceptor } from './auth-interceptor';
import { Session } from './session';

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let session: Session;
  let navegar: jasmine.Spy;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    session = TestBed.inject(Session);
    navegar = spyOn(TestBed.inject(Router), 'navigate').and.resolveTo(true);
  });

  afterEach(() => {
    backend.verify();
    localStorage.clear();
  });

  function falhar(url: string, status: number): void {
    http.get(url).subscribe({ error: () => undefined });
    backend.expectOne(url).flush({ detail: 'x' }, { status, statusText: 'erro' });
  }

  it('põe o token em toda chamada', () => {
    session.abrir('abc');
    http.get('/api/v1/me').subscribe();

    const req = backend.expectOne('/api/v1/me');
    expect(req.request.headers.get('Authorization')).toBe('Bearer abc');
    req.flush({});
  });

  it('401 com sessão fecha a sessão e leva para /entrar', () => {
    session.abrir('abc');

    falhar('/api/v1/me', 401);

    expect(session.token).toBeNull();
    expect(navegar).toHaveBeenCalledWith(['/entrar']);
  });

  it('401 sem token numa rota de aluno também leva para /entrar e apaga o menu', () => {
    session.abrir('abc');
    localStorage.removeItem('mentor-ai.token');

    falhar('/api/v1/tasks/t1/progress', 401);

    expect(session.autenticado()).toBeFalse();
    expect(navegar).toHaveBeenCalledWith(['/entrar']);
  });

  it('link de login já usado não derruba a sessão que está aberta', () => {
    session.abrir('abc');

    falhar('/api/v1/auth/verify', 401);
    falhar('/api/v1/auth/magic-link', 401);

    expect(session.token).toBe('abc');
    expect(navegar).not.toHaveBeenCalled();
  });

  it('403 do painel de admin não derruba a sessão do aluno', () => {
    session.abrir('abc');

    falhar('/api/v1/admin/metrics', 403);

    expect(session.token).toBe('abc');
  });
});
