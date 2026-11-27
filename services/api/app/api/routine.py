"""Minha rotina: a agenda da semana e as séries de compromissos do aluno.

O endpoint não carrega regra: traduz o corpo, chama o serviço e devolve o que
ele respondeu. O aluno vem da sessão; série de outro aluno responde 404.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import get_session
from ..deps import current_student
from ..models import Student
from ..routine import (
    RoutineError,
    RoutineWeek,
    SaveResult,
    SeriesInput,
    SeriesNotFound,
    create_series,
    delete_series,
    update_series,
    week_view,
)

#: O nome da constante mudou entre versões do Starlette; o número, não.
UNPROCESSABLE = 422

router = APIRouter(prefix="/api/v1")

CommitmentKind = Literal["aula", "plantao", "academia", "trabalho", "leitura", "outro"]
#: Horário sai como "HH:MM", que é o que a agenda e o `<input type="time">` usam.
Clock = Annotated[time, PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str)]


class CommitmentSeriesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CommitmentKind
    label: str = Field(default="", max_length=160)
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    on_day: date | None = None
    starts_at: time | None = None
    duration_minutes: int = Field(ge=1, le=24 * 60)
    starts_on: date | None = None
    ends_on: date | None = None

    def as_input(self) -> SeriesInput:
        return SeriesInput(
            kind=self.kind,
            label=self.label,
            weekdays=tuple(self.weekdays),
            on_day=self.on_day,
            starts_at=self.starts_at,
            duration_minutes=self.duration_minutes,
            starts_on=self.starts_on,
            ends_on=self.ends_on,
        )


class SeriesOut(BaseModel):
    """A série como ela vale de amanhã em diante, no mesmo formato do corpo de escrita."""

    kind: str
    label: str
    weekdays: list[int]
    on_day: date | None
    starts_at: Clock | None
    duration_minutes: int
    starts_on: date | None
    ends_on: date | None


class SaveOut(BaseModel):
    series_id: uuid.UUID | None
    replan_summary: str


class RoutineItemOut(BaseModel):
    series_id: uuid.UUID
    kind: str
    label: str
    starts_at: Clock | None
    duration_minutes: int
    recurring: bool
    document_name: str | None
    edited_by_student: bool
    editable: bool
    ends_on: date | None
    series: SeriesOut | None


class RoutineDayOut(BaseModel):
    day: date
    free_minutes: int
    light: bool
    computed: bool
    items: list[RoutineItemOut]


class RoutineWeekOut(BaseModel):
    week_start: date
    today: date
    changed_today: bool
    days: list[RoutineDayOut]


def _week_out(semana: RoutineWeek) -> RoutineWeekOut:
    return RoutineWeekOut(
        week_start=semana.week_start,
        today=semana.today,
        changed_today=semana.changed_today,
        days=[
            RoutineDayOut(
                day=dia.day,
                free_minutes=dia.free_minutes,
                light=dia.light,
                computed=dia.computed,
                items=[
                    RoutineItemOut(
                        series_id=item.series_id,
                        kind=item.kind,
                        label=item.label,
                        starts_at=item.starts_at,
                        duration_minutes=item.duration_minutes,
                        recurring=item.recurring,
                        document_name=item.document_name,
                        edited_by_student=item.edited_by_student,
                        editable=item.editable,
                        ends_on=item.ends_on,
                        series=_series_out(item.series),
                    )
                    for item in dia.items
                ],
            )
            for dia in semana.days
        ],
    )


def _series_out(serie: SeriesInput | None) -> SeriesOut | None:
    if serie is None:
        return None
    return SeriesOut(
        kind=serie.kind,
        label=serie.label,
        weekdays=list(serie.weekdays),
        on_day=serie.on_day,
        starts_at=serie.starts_at,
        duration_minutes=serie.duration_minutes,
        starts_on=serie.starts_on,
        ends_on=serie.ends_on,
    )


def _save_out(resultado: SaveResult) -> SaveOut:
    return SaveOut(series_id=resultado.series_id, replan_summary=resultado.replan_summary)


def _translate(erro: RoutineError) -> HTTPException:
    if isinstance(erro, SeriesNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(erro))
    return HTTPException(UNPROCESSABLE, str(erro))


@router.get("/me/routine", response_model=RoutineWeekOut)
def get_routine(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
    week: date | None = None,
) -> RoutineWeekOut:
    """A semana de segunda a domingo: compromissos e quanto sobra para estudo."""
    hoje = today_in(student.timezone)
    try:
        semana = week_view(session, student, week or hoje, today=hoje)
    except RoutineError as erro:
        raise _translate(erro) from erro
    return _week_out(semana)


@router.post("/me/commitment-series", response_model=SaveOut, status_code=status.HTTP_201_CREATED)
def post_series(
    payload: CommitmentSeriesIn,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SaveOut:
    try:
        resultado = create_series(
            session, student, payload.as_input(), today=today_in(student.timezone)
        )
    except RoutineError as erro:
        raise _translate(erro) from erro
    return _save_out(resultado)


@router.patch("/me/commitment-series/{series_id}", response_model=SaveOut)
def patch_series(
    series_id: uuid.UUID,
    payload: CommitmentSeriesIn,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SaveOut:
    try:
        resultado = update_series(
            session, student, series_id, payload.as_input(), today=today_in(student.timezone)
        )
    except RoutineError as erro:
        raise _translate(erro) from erro
    return _save_out(resultado)


@router.delete("/me/commitment-series/{series_id}", response_model=SaveOut)
def delete_series_route(
    series_id: uuid.UUID,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SaveOut:
    try:
        resultado = delete_series(session, student, series_id, today=today_in(student.timezone))
    except RoutineError as erro:
        raise _translate(erro) from erro
    return _save_out(resultado)
