from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PlanTaskOut(BaseModel):
    id: uuid.UUID
    kind: Literal["teoria", "questoes", "revisao", "simulado"]
    topic: str
    minutes: int
    status: Literal["pendente", "feita", "nao_deu"]


class DayPlanOut(BaseModel):
    date: date
    capacity_minutes: int
    light: bool
    plan_version: int
    tasks: list[PlanTaskOut]


class ProgressIn(BaseModel):
    action: Literal["feita", "nao_deu"]
    answered: int | None = Field(default=None, ge=0, le=1000)
    correct: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def check_counts(self) -> ProgressIn:
        if self.correct is not None and self.answered is None:
            raise ValueError("acertos sem o total de questões feitas")
        if self.answered is not None and self.correct is not None and self.correct > self.answered:
            raise ValueError("acertos não podem passar das questões feitas")
        return self


class SubtemaOut(BaseModel):
    slug: str
    name: str
    incidence: float


class TemaOut(BaseModel):
    slug: str
    name: str
    subtemas: list[SubtemaOut]


class AreaOut(BaseModel):
    slug: str
    name: str
    temas: list[TemaOut]


class CatalogOut(BaseModel):
    exam: str
    exam_name: str
    weights_source: str
    areas: list[AreaOut]


class ProjectionOut(BaseModel):
    """O plano cabe até a prova? E, se não cabe, o que oferecer ao aluno."""

    fits: bool
    exam_date: date
    days_left: int
    planned_minutes: int
    available_minutes: int
    missing_minutes: int
    extra_minutes_per_day: int
    #: Subtemas que não couberam, do menos prioritário para o mais prioritário.
    unscheduled_topics: list[str]


class ReplanOut(BaseModel):
    plan_version: int
    summary: str
    created: int
    removed: int
    fits: bool
