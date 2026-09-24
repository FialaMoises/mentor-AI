"""Modelo de dados — fatia inicial da especificação v0.1.

Nomes de domínio seguem a spec (Tema, ProvaAlvo) traduzidos para inglês nos
identificadores, com o termo da spec no comentário de cada tabela.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

TASK_KINDS = ("teoria", "questoes", "revisao", "simulado")
TASK_STATUSES = ("pendente", "feita", "nao_deu")
PROGRESS_ACTIONS = ("feita", "nao_deu")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Student(Base):
    """Aluno."""

    __tablename__ = "student"

    id: Mapped[uuid.UUID] = _uuid_pk()
    phase: Mapped[str] = mapped_column(String(20))  # faculdade | formado
    mode: Mapped[str] = mapped_column(String(20))  # cursinho | independente
    timezone: Mapped[str] = mapped_column(String(64), default="America/Fortaleza")
    subscription_status: Mapped[str] = mapped_column(String(20), default="trial")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("phase in ('faculdade','formado')", name="ck_student_phase"),
        CheckConstraint("mode in ('cursinho','independente')", name="ck_student_mode"),
    )


class TargetExam(Base):
    """ProvaAlvo. Só uma principal por aluno."""

    __tablename__ = "target_exam"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    exam_date: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(Base):
    """Tema da base canônica, igual para todos os alunos."""

    __tablename__ = "topic"

    id: Mapped[uuid.UUID] = _uuid_pk()
    area: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topic.id", ondelete="SET NULL"), nullable=True
    )
    incidence: Mapped[float] = mapped_column(Float, default=1.0)


class Proficiency(Base):
    """Proficiencia do aluno num tema."""

    __tablename__ = "proficiency"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"))
    self_assessment: Mapped[float] = mapped_column(Float, default=0.5)
    answered: Mapped[int] = mapped_column(Integer, default=0)
    correct: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("student_id", "topic_id", name="uq_proficiency_student_topic"),
    )


class DailyCapacity(Base):
    """CapacidadeDiaria, derivada dos compromissos confirmados."""

    __tablename__ = "daily_capacity"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    free_minutes: Mapped[int] = mapped_column(Integer)
    light: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("student_id", "day", name="uq_capacity_student_day"),)


class PlanVersion(Base):
    """VersaoPlano. Cada replanejamento gera uma."""

    __tablename__ = "plan_version"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("student_id", "number", name="uq_plan_version_number"),)


class Task(Base):
    """Tarefa de um dia."""

    __tablename__ = "task"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    plan_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_version.id", ondelete="CASCADE")
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    day: Mapped[date] = mapped_column(Date, index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pendente")

    topic: Mapped[Topic] = relationship(lazy="joined")
    plan_version: Mapped[PlanVersion] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(f"kind in {TASK_KINDS}", name="ck_task_kind"),
        CheckConstraint(f"status in {TASK_STATUSES}", name="ck_task_status"),
    )


class ProgressEvent(Base):
    """EventoProgresso: histórico imutável, o dado mais valioso do sistema."""

    __tablename__ = "progress_event"

    id: Mapped[uuid.UUID] = _uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(20))
    answered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (CheckConstraint(f"action in {PROGRESS_ACTIONS}", name="ck_progress_action"),)
