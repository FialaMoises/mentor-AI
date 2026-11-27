"""O que o LLM pode devolver. Nada entra no banco sem passar por aqui.

A saída do modelo é dado não confiável: campo que não está neste schema é
recusado, e valor fora da faixa derruba a extração inteira.
"""

from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CommitmentKind = Literal["aula", "plantao", "academia", "trabalho", "leitura", "outro"]


class ExtractedCommitment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CommitmentKind
    label: str = Field(default="", max_length=160)
    weekday: int | None = Field(default=None, ge=0, le=6)
    on_day: date | None = None
    duration_minutes: int = Field(ge=1, le=24 * 60)
    starts_on: date | None = None
    ends_on: date | None = None
    #: Horário de início ("HH:MM"), só quando o arquivo disser.
    starts_at: time | None = None

    @model_validator(mode="after")
    def semanal_ou_data_unica(self) -> ExtractedCommitment:
        if (self.weekday is None) == (self.on_day is None):
            raise ValueError("compromisso é semanal (weekday) ou de data única (on_day)")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("vigência termina antes de começar")
        return self


class ExtractedExam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    exam_date: date


class RoutineExtraction(BaseModel):
    """A semana do aluno como o modelo leu o arquivo."""

    model_config = ConfigDict(extra="forbid")

    commitments: list[ExtractedCommitment] = Field(default_factory=list, max_length=200)
    exams: list[ExtractedExam] = Field(default_factory=list, max_length=20)
    #: O que o modelo não conseguiu ler — vira aviso na tela de confirmação.
    unreadable: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def tem_alguma_coisa(self) -> RoutineExtraction:
        if not self.commitments and not self.exams and not self.unreadable:
            raise ValueError("extração vazia: nem compromisso, nem prova, nem aviso")
        return self
