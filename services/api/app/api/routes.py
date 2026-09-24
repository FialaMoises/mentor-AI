"""Rotas da fase 0: ler a lista do dia e marcar progresso.

Fase 0 roda sem autenticação, com o aluno do seed. O ponto de costura está em
`resolve_student`: quando a fase 3 trouxer o login, o escopo por aluno passa a
valer para todas as rotas mudando só essa função.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import get_session
from ..models import DailyCapacity, Proficiency, ProgressEvent, Student, Task
from ..schemas import DayPlanOut, PlanTaskOut, ProgressIn

router = APIRouter(prefix="/api/v1")


def resolve_student(student_id: uuid.UUID, session: Session) -> Student:
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "aluno não encontrado")
    return student


@router.get("/students/{student_id}/plan/today", response_model=DayPlanOut)
def read_today(
    student_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]
) -> DayPlanOut:
    student = resolve_student(student_id, session)
    day = today_in(student.timezone)

    capacity = session.scalar(
        select(DailyCapacity).where(
            DailyCapacity.student_id == student.id, DailyCapacity.day == day
        )
    )
    tasks = list(
        session.scalars(
            select(Task)
            .where(Task.student_id == student.id, Task.day == day)
            .order_by(Task.position, Task.id)
        )
    )

    return DayPlanOut(
        date=day,
        capacity_minutes=capacity.free_minutes if capacity else 0,
        light=capacity.light if capacity else False,
        plan_version=max((t.plan_version.number for t in tasks), default=0),
        tasks=[
            PlanTaskOut(
                id=task.id,
                kind=task.kind,
                topic=task.topic.name,
                minutes=task.minutes,
                status=task.status,
            )
            for task in tasks
        ],
    )


@router.post("/tasks/{task_id}/progress", response_model=PlanTaskOut)
def mark_progress(
    task_id: uuid.UUID,
    payload: ProgressIn,
    session: Annotated[Session, Depends(get_session)],
) -> PlanTaskOut:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tarefa não encontrada")

    task.status = payload.action
    session.add(
        ProgressEvent(
            task_id=task.id,
            action=payload.action,
            answered=payload.answered,
            correct=payload.correct,
        )
    )

    if payload.answered:
        proficiency = session.scalar(
            select(Proficiency).where(
                Proficiency.student_id == task.student_id,
                Proficiency.topic_id == task.topic_id,
            )
        )
        if proficiency is not None:
            proficiency.answered += payload.answered
            proficiency.correct += payload.correct or 0

    session.flush()
    return PlanTaskOut(
        id=task.id,
        kind=task.kind,
        topic=task.topic.name,
        minutes=task.minutes,
        status=task.status,
    )
