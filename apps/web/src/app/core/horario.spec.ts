import { duracaoEntre, fimDe, hhmm, minutosDe } from './horario';

describe('horario', () => {
  it('converte HH:MM em minutos e de volta', () => {
    expect(minutosDe('07:30')).toBe(450);
    expect(hhmm(450)).toBe('07:30');
  });

  it('dá a volta no relógio para os dois lados', () => {
    expect(hhmm(-30)).toBe('23:30');
    expect(hhmm(1440)).toBe('00:00');
    expect(fimDe('19:00', 720)).toBe('07:00');
  });

  it('duração que passa da meia-noite', () => {
    expect(duracaoEntre('22:00', '06:00')).toBe(480);
  });

  it('início igual ao fim é um dia inteiro (24h), não zero', () => {
    expect(duracaoEntre('07:00', '07:00')).toBe(1440);
  });
});
