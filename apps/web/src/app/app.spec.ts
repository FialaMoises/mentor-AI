import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';
import { routes } from './app.routes';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes)],
    }).compileComponents();
  });

  it('monta a casca com a marca', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    const brand = fixture.nativeElement.querySelector('.brand') as HTMLElement;
    expect(brand.textContent).toContain('mentor-AI');
  });
});
