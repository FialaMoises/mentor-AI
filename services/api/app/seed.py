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
from .models import (
    DailyCapacity,
    Exam,
    Proficiency,
    ProgressEvent,
    Student,
    TargetExam,
    Task,
    Topic,
    TopicIncidence,
)
from .planning import replan

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

    # O seed usa o mesmo caminho do replanejamento: o dia de hoje entra junto.
    task_ids = list(
        session.scalars(select(Task.id).where(Task.student_id == student.id, Task.day >= day))
    )
    if task_ids:
        session.execute(delete(ProgressEvent).where(ProgressEvent.task_id.in_(task_ids)))
        session.execute(delete(Task).where(Task.id.in_(task_ids)))
    session.flush()

    replan(session, student, day, reason="seed", from_tomorrow=False)


def main() -> None:
    with SessionLocal() as session:
        run(session)
        session.commit()
    print(f"seed pronto para o aluno {SEED_STUDENT_ID}")


if __name__ == "__main__":
    main()
