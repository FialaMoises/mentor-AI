"""Tipos do motor de planejamento.

Este pacote é puro: nada aqui importa banco, rede, S3, LLM ou relógio.
Data, capacidade e parâmetros entram por argumento — mesma entrada, mesmo plano.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class TaskKind(StrEnum):
    TEORIA = "teoria"
    QUESTOES = "questoes"
    REVISAO = "revisao"
    SIMULADO = "simulado"


class StudyMode(StrEnum):
    CURSINHO = "cursinho"
    INDEPENDENTE = "independente"


#: Ordem de desempate entre tarefas de mesma prioridade. Revisão vencida vem
#: antes de tudo; teoria vem antes das questões do mesmo tema.
KIND_ORDER: dict[TaskKind, int] = {
    TaskKind.REVISAO: 0,
    TaskKind.TEORIA: 1,
    TaskKind.QUESTOES: 2,
    TaskKind.SIMULADO: 3,
}

#: Num dia leve (véspera pesada ou dia seguinte a plantão de 24h) o aluno só
#: recebe revisão e questões — nunca teoria nova ou simulado.
LIGHT_DAY_KINDS: frozenset[TaskKind] = frozenset({TaskKind.REVISAO, TaskKind.QUESTOES})


@dataclass(frozen=True, slots=True)
class EngineParams:
    """Parâmetros de calibração. Nunca constantes espalhadas pelo código."""

    k: float = 10.0
    review_offsets_days: tuple[int, ...] = (1, 7, 30)
    inactivity_days: int = 5
    #: Quanto do dia dá para usar para estudo, antes de descontar compromisso.
    #: Não é a meta do aluno: é o teto físico do dia, depois de dormir e viver.
    study_window_minutes: int = 600
    exam_horizon_days: int = 365
    theory_minutes: int = 50
    questions_minutes: int = 30
    review_minutes: int = 20
    #: Semana de retomada: fração da capacidade no primeiro dia e quanto sobe por dia.
    restart_floor: float = 0.5
    restart_step: float = 0.1
    restart_days: int = 7

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k deve ser maior que zero")
        if self.exam_horizon_days <= 0:
            raise ValueError("exam_horizon_days deve ser maior que zero")
        if not self.review_offsets_days:
            raise ValueError("sem intervalos de revisão o motor não agenda revisão")
        if any(offset <= 0 for offset in self.review_offsets_days):
            raise ValueError("intervalo de revisão precisa ser positivo")
        if not 0 < self.restart_floor <= 1:
            raise ValueError("restart_floor vai de 0 (exclusivo) a 1")
        if not 0 < self.study_window_minutes <= 24 * 60:
            raise ValueError("study_window_minutes vai de 1 minuto a um dia")

    def minutes_for(self, kind: TaskKind) -> int:
        return {
            TaskKind.TEORIA: self.theory_minutes,
            TaskKind.QUESTOES: self.questions_minutes,
            TaskKind.REVISAO: self.review_minutes,
            TaskKind.SIMULADO: 180,
        }[kind]


@dataclass(frozen=True, slots=True)
class TopicState:
    """O que o motor sabe sobre um tema para um aluno, num instante."""

    topic_id: str
    incidence: float
    self_assessment: float
    answered: int = 0
    correct: int = 0
    review_due_days: int | None = None
    #: Dia em que a teoria do tema foi estudada. None = ainda não estudou.
    studied_on: date | None = None
    #: Quantas revisões desse tema já foram feitas.
    reviews_done: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.self_assessment <= 1.0:
            raise ValueError("self_assessment vai de 0 a 1")
        if self.answered < 0 or self.correct < 0:
            raise ValueError("questões e acertos não podem ser negativos")
        if self.correct > self.answered:
            raise ValueError("acertos não podem passar das questões feitas")
        if self.reviews_done < 0:
            raise ValueError("reviews_done não pode ser negativo")


@dataclass(frozen=True, slots=True)
class DayCapacity:
    """Minutos livres de um dia, já descontados os compromissos.

    Um dia de prova secundária entra aqui com `free_minutes=0`; a véspera, como
    dia leve.
    """

    day: date
    free_minutes: int
    light: bool = False

    def __post_init__(self) -> None:
        if self.free_minutes < 0:
            raise ValueError("free_minutes não pode ser negativo")

    def with_minutes(self, minutes: int) -> DayCapacity:
        return DayCapacity(day=self.day, free_minutes=minutes, light=self.light)


@dataclass(frozen=True, slots=True)
class Candidate:
    """Uma tarefa que o motor pode colocar no dia."""

    topic_id: str
    kind: TaskKind
    minutes: int

    def __post_init__(self) -> None:
        if self.minutes <= 0:
            raise ValueError("minutes deve ser maior que zero")


@dataclass(frozen=True, slots=True)
class PlannedTask:
    """Uma tarefa já colocada num dia, com a prioridade que a colocou lá."""

    day: date
    topic_id: str
    kind: TaskKind
    minutes: int
    priority: float
    #: Qual revisão do tema é esta (0 = a primeira do `review_offsets_days`).
    review_index: int | None = None


@dataclass(frozen=True, slots=True)
class Projection:
    """O plano cabe até a prova? E, se não cabe, o que oferecer ao aluno."""

    fits: bool
    planned_minutes: int
    available_minutes: int
    missing_minutes: int
    days_left: int
    #: Temas que não couberam, do menos prioritário para o mais prioritário.
    unscheduled_topics: tuple[str, ...] = ()

    @property
    def extra_minutes_per_day(self) -> int:
        """Quanto o aluno teria que somar por dia para o plano caber."""
        if self.fits or self.days_left <= 0:
            return 0
        return -(-self.missing_minutes // self.days_left)


@dataclass(frozen=True, slots=True)
class HorizonPlan:
    """O plano inteiro, do dia inicial até a prova."""

    tasks: tuple[PlannedTask, ...]
    unscheduled: tuple[Candidate, ...]
    projection: Projection
