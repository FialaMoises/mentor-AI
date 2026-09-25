"""Seed determinístico: um aluno de exemplo com a lista de hoje já planejada.

Roda com `python -m app.seed` e carrega a base canônica antes, se ainda não
estiver no banco. Os ids são fixos para que testes, demos e o front da fase 0
apontem sempre para o mesmo aluno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .catalog import load as load_catalog
from .clock import today_in
from .db import SessionLocal
from .engine import Candidate, DayCapacity, EngineParams, TaskKind, TopicState, fill_day
from .models import (
    DailyCapacity,
    Exam,
    PlanVersion,
    Proficiency,
    ProgressEvent,
    Student,
    TargetExam,
    Task,
    Topic,
    TopicIncidence,
)

SEED_STUDENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SEED_EXAM_SLUG = "enamed"

#: Subtemas do catálogo com a autoavaliação inicial do aluno de exemplo.
SEED_SELF_ASSESSMENT: dict[str, float] = {
    "insuficiencia-cardiaca": 0.4,
    "diabetes-mellitus": 0.6,
    "ictericia-neonatal": 0.3,
    "apendicite-aguda": 0.5,
    "pre-natal-de-risco-habitual": 0.7,
    "medidas-de-frequencia": 0.2,
}


def run(session: Session, today: date | None = None) -> None:
    load_catalog(session)

    exam = session.scalar(select(Exam).where(Exam.slug == SEED_EXAM_SLUG))
    if exam is None:  # pragma: no cover - o catálogo acabou de criar a prova
        raise RuntimeError(f"prova {SEED_EXAM_SLUG!r} não está no catálogo")

    student = session.get(Student, SEED_STUDENT_ID)
    if student is None:
        student = Student(
            id=SEED_STUDENT_ID,
            phase="formado",
            mode="independente",
            timezone="America/Fortaleza",
            subscription_status="trial",
        )
        session.add(student)
        session.flush()

    day = today or today_in(student.timezone)
    exam_date = day + timedelta(days=120)

    target = session.scalar(
        select(TargetExam).where(TargetExam.student_id == student.id, TargetExam.exam_id == exam.id)
    )
    if target is None:
        target = TargetExam(student_id=student.id, exam_id=exam.id, name=exam.name)
        session.add(target)
    target.exam_date = exam_date
    target.is_primary = True
    session.flush()

    topics: dict[str, TopicState] = {}
    for slug, self_assessment in SEED_SELF_ASSESSMENT.items():
        topic = session.scalar(select(Topic).where(Topic.slug == slug))
        if topic is None:  # pragma: no cover - slug tem que existir no catálogo
            raise RuntimeError(f"subtema {slug!r} não está na base canônica")

        incidence = session.scalar(
            select(TopicIncidence).where(
                TopicIncidence.topic_id == topic.id, TopicIncidence.exam_id == exam.id
            )
        )
        if incidence is None:  # pragma: no cover - o catálogo dá peso a todo subtema
            raise RuntimeError(f"subtema {slug!r} sem incidência para {exam.slug}")

        existing = session.scalar(
            select(Proficiency).where(
                Proficiency.student_id == student.id, Proficiency.topic_id == topic.id
            )
        )
        if existing is None:
            session.add(
                Proficiency(
                    student_id=student.id,
                    topic_id=topic.id,
                    self_assessment=self_assessment,
                )
            )
        topics[str(topic.id)] = TopicState(
            topic_id=str(topic.id),
            incidence=incidence.weight,
            self_assessment=self_assessment,
        )
    session.flush()

    capacity = session.scalar(
        select(DailyCapacity).where(
            DailyCapacity.student_id == student.id, DailyCapacity.day == day
        )
    )
    if capacity is None:
        capacity = DailyCapacity(student_id=student.id, day=day, free_minutes=180, light=False)
        session.add(capacity)
        session.flush()

    # O plano de hoje é regerado a cada seed, junto com o histórico do dia.
    task_ids = list(
        session.scalars(select(Task.id).where(Task.student_id == student.id, Task.day == day))
    )
    if task_ids:
        session.execute(delete(ProgressEvent).where(ProgressEvent.task_id.in_(task_ids)))
        session.execute(delete(Task).where(Task.id.in_(task_ids)))

    version_number = (
        session.scalar(
            select(PlanVersion.number)
            .where(PlanVersion.student_id == student.id)
            .order_by(PlanVersion.number.desc())
        )
        or 0
    ) + 1
    plan_version = PlanVersion(
        student_id=student.id,
        number=version_number,
        reason="seed",
        summary="Plano inicial do aluno de exemplo.",
    )
    session.add(plan_version)
    session.flush()

    candidates = [
        Candidate(topic_id=topic_id, kind=kind, minutes=minutes)
        for topic_id in topics
        for kind, minutes in ((TaskKind.TEORIA, 50), (TaskKind.QUESTOES, 30))
    ]
    planned = fill_day(
        capacity=DayCapacity(day=day, free_minutes=capacity.free_minutes, light=capacity.light),
        candidates=candidates,
        topics=topics,
        exam_date=exam_date,
        params=EngineParams(),
    )

    for position, task in enumerate(planned):
        session.add(
            Task(
                student_id=student.id,
                plan_version_id=plan_version.id,
                topic_id=uuid.UUID(task.topic_id),
                kind=task.kind.value,
                day=task.day,
                minutes=task.minutes,
                position=position,
                status="pendente",
            )
        )


def main() -> None:
    with SessionLocal() as session:
        run(session)
        session.commit()
    print(f"seed pronto para o aluno {SEED_STUDENT_ID}")


if __name__ == "__main__":
    main()
