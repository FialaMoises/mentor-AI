"""Da rotina do aluno para a capacidade de cada dia.

Puro como o resto do motor: entram compromissos e um orçamento diário, sai a
lista de `DayCapacity`. Nada de banco, nada de relógio.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .types import DayCapacity, EngineParams

#: Um plantão a partir daqui é plantão longo: o dia seguinte vira dia leve.
LONG_SHIFT_MINUTES = 12 * 60


@dataclass(frozen=True, slots=True)
class Commitment:
    """Um compromisso da rotina: aula, plantão, academia, trabalho.

    `weekday` (0 = segunda) marca o que se repete toda semana; `on_day` marca o
    compromisso de data única. Um dos dois, nunca os dois.
    """

    kind: str
    duration_minutes: int
    weekday: int | None = None
    on_day: date | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("compromisso sem duração")
        if self.duration_minutes > 24 * 60:
            raise ValueError("compromisso maior que um dia")
        if (self.weekday is None) == (self.on_day is None):
            raise ValueError("compromisso é semanal (weekday) ou de data única (on_day)")
        if self.weekday is not None and not 0 <= self.weekday <= 6:
            raise ValueError("weekday vai de 0 (segunda) a 6 (domingo)")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("vigência termina antes de começar")

    @property
    def is_long_shift(self) -> bool:
        return self.duration_minutes >= LONG_SHIFT_MINUTES

    def happens_on(self, day: date) -> bool:
        if self.starts_on and day < self.starts_on:
            return False
        if self.ends_on and day > self.ends_on:
            return False
        if self.on_day is not None:
            return self.on_day == day
        return self.weekday == day.weekday()


def busy_minutes(commitments: Sequence[Commitment], day: date) -> int:
    return sum(c.duration_minutes for c in commitments if c.happens_on(day))


def capacities_from_commitments(
    days: Sequence[date],
    commitments: Sequence[Commitment],
    daily_budget_minutes: int,
    params: EngineParams | None = None,
) -> list[DayCapacity]:
    """Quanto sobra para estudar em cada dia.

    São duas contas diferentes. O orçamento diário é a meta que o aluno se pôs
    ("quero estudar 14 horas por semana"); a janela de estudo é o quanto do dia
    dá para usar. O compromisso come a janela, não a meta: seis horas de
    enfermaria ainda deixam as duas horas de estudo de pé, doze de plantão não.

    O dia seguinte a um plantão longo vira dia leve, mesmo que esteja livre: o
    aluno acabou de virar a noite.
    """
    params = params or EngineParams()
    if daily_budget_minutes < 0:
        raise ValueError("orçamento diário não pode ser negativo")

    saída: list[DayCapacity] = []
    for day in sorted(days):
        ocupado = busy_minutes(commitments, day)
        sobra_do_dia = max(0, params.study_window_minutes - ocupado)
        livre = min(daily_budget_minutes, sobra_do_dia)
        véspera = day - timedelta(days=1)
        leve = any(c.is_long_shift and c.happens_on(véspera) for c in commitments)
        saída.append(DayCapacity(day=day, free_minutes=livre, light=leve))
    return saída


def daily_budget(hours_per_week: float) -> int:
    """Horas por semana viram minutos por dia, arredondando para baixo."""
    if hours_per_week < 0:
        raise ValueError("horas por semana não pode ser negativo")
    return int(hours_per_week * 60 / 7)
