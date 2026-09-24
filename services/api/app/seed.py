"""Seed determinístico: um aluno de exemplo com a lista de hoje já planejada.

Roda com `python -m app.seed`. Os ids são fixos para que testes, demos e o
front da fase 0 apontem sempre para o mesmo aluno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .clock import today_in
from .db import SessionLocal
from .engine import Candidate, DayCapacity, EngineParams, TaskKind, TopicState, fill_day
from .models import DailyCapacity, PlanVersion, Proficiency, ProgressEvent, Student, Task, Topic

SEED_STUDENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

SEED_TOPICS: list[tuple[str, str, str, float, float]] = [
    # (id sufixo, área, tema, incidência, autoavaliação)
    ("aaaa0001", "Clínica médica", "Insuficiência cardíaca", 0.9, 0.4),
    ("aaaa0002", "Clínica médica", "Diabetes mellitus", 0.8, 0.6),
    ("aaaa0003", "Pediatria", "Icterícia neonatal", 0.6, 0.3),
    ("aaaa0004", "Cirurgia", "Abdome agudo", 0.7, 0.5),
    ("aaaa0005", "Ginecologia e obstetrícia", "Pré-natal de risco habitual", 0.7, 0.7),
    ("aaaa0006", "Preventiva", "Indicadores de saúde", 0.5, 0.2),
]


def _topic_id(suffix: str) -> uuid.UUID:
    return uuid.UUID(f"{suffix}-0000-4000-8000-000000000000")


def run(session: Session, today: date | None = None) -> None:
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

    day = today or today_in(student.timezone)
    exam_date = day + timedelta(days=120)

    # Os temas entram antes das proficiências: a proficiência aponta para o tema.
    for suffix, area, name, incidence, _ in SEED_TOPICS:
        topic_id = _topic_id(suffix)
        if session.get(Topic, topic_id) is None:
            session.add(Topic(id=topic_id, area=area, name=name, incidence=incidence))
    session.flush()

    topics: dict[str, TopicState] = {}
    for suffix, _area, _name, incidence, self_assessment in SEED_TOPICS:
        topic_id = _topic_id(suffix)
        existing = session.scalar(
            select(Proficiency).where(
                Proficiency.student_id == student.id, Proficiency.topic_id == topic_id
            )
        )
        if existing is None:
            session.add(
                Proficiency(
                    student_id=student.id,
                    topic_id=topic_id,
                    self_assessment=self_assessment,
                )
            )
        topics[str(topic_id)] = TopicState(
            topic_id=str(topic_id),
            incidence=incidence,
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
