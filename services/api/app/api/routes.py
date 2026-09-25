"""Plano do dia, projeção, replanejamento e catálogo.

O aluno vem da sessão, nunca da URL: não existe rota onde dá para pedir o plano
de outra pessoa trocando um id. A tarefa marcada é conferida contra o dono.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import today_in
from ..db import get_session
from ..deps import current_student
from ..models import (
    TOPIC_LEVEL_AREA,
    TOPIC_LEVEL_SUBTEMA,
    TOPIC_LEVEL_TEMA,
    DailyCapacity,
    Exam,
    Student,
    Task,
    Topic,
    TopicIncidence,
)
from ..planning import PlanningError, primary_exam, project, replan
from ..progress import apply_progress
from ..schemas import (
    AreaOut,
    CatalogOut,
    DayPlanOut,
    PlanTaskOut,
    ProgressIn,
    ProjectionOut,
    ReplanOut,
    SubtemaOut,
    TemaOut,
)

router = APIRouter(prefix="/api/v1")


@router.get("/catalog/{exam_slug}", response_model=CatalogOut)
def read_catalog(exam_slug: str, session: Annotated[Session, Depends(get_session)]) -> CatalogOut:
    """A base canônica como o aluno vai vê-la na autoavaliação: árvore e pesos."""
    exam = session.scalar(select(Exam).where(Exam.slug == exam_slug))
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prova não encontrada")

    topics = list(session.scalars(select(Topic).order_by(Topic.level, Topic.position, Topic.name)))
    incidences = {
        row.topic_id: row
        for row in session.scalars(select(TopicIncidence).where(TopicIncidence.exam_id == exam.id))
    }

    filhos: dict[uuid.UUID, list[Topic]] = {}
    for topic in topics:
        if topic.parent_id is not None:
            filhos.setdefault(topic.parent_id, []).append(topic)

    fonte = next((row.source for row in incidences.values()), "")
    areas = [
        AreaOut(
            slug=area.slug,
            name=area.name,
            temas=[
                TemaOut(
                    slug=tema.slug,
                    name=tema.name,
                    subtemas=[
                        SubtemaOut(
                            slug=sub.slug,
                            name=sub.name,
                            incidence=incidences[sub.id].weight if sub.id in incidences else 0.0,
                        )
                        for sub in filhos.get(tema.id, [])
                        if sub.level == TOPIC_LEVEL_SUBTEMA
                    ],
                )
                for tema in filhos.get(area.id, [])
                if tema.level == TOPIC_LEVEL_TEMA
            ],
        )
        for area in topics
        if area.level == TOPIC_LEVEL_AREA
    ]

    return CatalogOut(exam=exam.slug, exam_name=exam.name, weights_source=fonte, areas=areas)


@router.get("/me/plan/today", response_model=DayPlanOut)
def read_today(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> DayPlanOut:
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


@router.get("/me/plan/projection", response_model=ProjectionOut)
def read_projection(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> ProjectionOut:
    """Responde à pergunta do aviso de estouro: isso cabe até a prova?"""
    try:
        alvo = primary_exam(session, student)
        plano = project(session, student, today_in(student.timezone))
    except PlanningError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro

    projecao = plano.projection
    nomes = {
        str(topic.id): topic.name
        for topic in session.scalars(
            select(Topic).where(Topic.id.in_([uuid.UUID(t) for t in projecao.unscheduled_topics]))
        )
    }
    return ProjectionOut(
        fits=projecao.fits,
        exam_date=alvo.exam_date,
        days_left=projecao.days_left,
        planned_minutes=projecao.planned_minutes,
        available_minutes=projecao.available_minutes,
        missing_minutes=projecao.missing_minutes,
        extra_minutes_per_day=projecao.extra_minutes_per_day,
        unscheduled_topics=[nomes.get(t, t) for t in projecao.unscheduled_topics],
    )


@router.post("/me/plan/replan", response_model=ReplanOut)
def request_replan(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> ReplanOut:
    """Replaneja na hora, de amanhã em diante. O dia de hoje continua congelado."""
    try:
        resultado = replan(session, student, today_in(student.timezone), reason="pedido do aluno")
    except PlanningError as erro:
        raise HTTPException(status.HTTP_409_CONFLICT, str(erro)) from erro

    return ReplanOut(
        plan_version=resultado.version.number,
        summary=resultado.version.summary,
        created=resultado.created,
        removed=resultado.removed,
        fits=resultado.fits,
    )


@router.post("/tasks/{task_id}/progress", response_model=PlanTaskOut)
def mark_progress(
    task_id: uuid.UUID,
    payload: ProgressIn,
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> PlanTaskOut:
    task = session.get(Task, task_id)
    # Tarefa de outro aluno responde 404, não 403: nem confirma que existe.
    if task is None or task.student_id != student.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tarefa não encontrada")

    apply_progress(
        session,
        task,
        action=payload.action,
        answered=payload.answered,
        correct=payload.correct,
        client_event_id=payload.client_event_id,
    )
    return PlanTaskOut(
        id=task.id,
        kind=task.kind,
        topic=task.topic.name,
        minutes=task.minutes,
        status=task.status,
    )
