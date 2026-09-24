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


#: Num dia leve (véspera pesada ou dia seguinte a plantão de 24h) o aluno só
#: recebe revisão e questões — nunca teoria nova ou simulado.
LIGHT_DAY_KINDS: frozenset[TaskKind] = frozenset({TaskKind.REVISAO, TaskKind.QUESTOES})


@dataclass(frozen=True, slots=True)
class EngineParams:
    """Parâmetros de calibração. Nunca constantes espalhadas pelo código."""

    k: float = 10.0
    review_offsets_days: tuple[int, ...] = (1, 7, 30)
    inactivity_days: int = 5
    exam_horizon_days: int = 365

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError("k deve ser maior que zero")
        if self.exam_horizon_days <= 0:
            raise ValueError("exam_horizon_days deve ser maior que zero")


@dataclass(frozen=True, slots=True)
class TopicState:
    """O que o motor sabe sobre um tema para um aluno, num instante."""

    topic_id: str
    incidence: float
    self_assessment: float
    answered: int = 0
    correct: int = 0
    review_due_days: int | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.self_assessment <= 1.0:
            raise ValueError("self_assessment vai de 0 a 1")
        if self.answered < 0 or self.correct < 0:
            raise ValueError("questões e acertos não podem ser negativos")
        if self.correct > self.answered:
            raise ValueError("acertos não podem passar das questões feitas")


@dataclass(frozen=True, slots=True)
class DayCapacity:
    """Minutos livres de um dia, já descontados os compromissos."""

    day: date
    free_minutes: int
    light: bool = False

    def __post_init__(self) -> None:
        if self.free_minutes < 0:
            raise ValueError("free_minutes não pode ser negativo")


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
