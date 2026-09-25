"""Modelo de dados — fatia inicial da especificação v0.1.

Nomes de domínio seguem a spec (Tema, ProvaAlvo) traduzidos para inglês nos
identificadores, com o termo da spec no comentário de cada tabela.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
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

TOPIC_LEVEL_AREA = 1
TOPIC_LEVEL_TEMA = 2
TOPIC_LEVEL_SUBTEMA = 3

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
    #: Horas de estudo por semana declaradas no questionário.
    weekly_hours: Mapped[int] = mapped_column(Integer, default=14)
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
    exam_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exam.id", ondelete="SET NULL"), nullable=True
    )
    exam_date: Mapped[date] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class Topic(Base):
    """Tema da base canônica, igual para todos os alunos.

    Árvore de três níveis: área (1) → tema (2) → subtema (3). O `slug` é a
    identidade estável entre o catálogo versionado e o banco.
    """

    __tablename__ = "topic"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    area: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    level: Mapped[int] = mapped_column(Integer, default=TOPIC_LEVEL_SUBTEMA)
    position: Mapped[int] = mapped_column(Integer, default=0)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topic.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (CheckConstraint("level between 1 and 3", name="ck_topic_level"),)


class Exam(Base):
    """Prova cujo peso por tema o motor usa (ENAMED, ENARE, provas estaduais)."""

    __tablename__ = "exam"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    authority: Mapped[str] = mapped_column(String(160), default="")
    notes: Mapped[str] = mapped_column(String(600), default="")


class TopicIncidence(Base):
    """IncidenciaTema: quanto um subtema pesa numa prova, e de onde veio esse peso.

    `source` nunca fica vazio: um peso sem origem registrada não entra na base.
    """

    __tablename__ = "topic_incidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    topic_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"))
    exam_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exam.id", ondelete="CASCADE"))
    weight: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(400))
    checked_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    topic: Mapped[Topic] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("topic_id", "exam_id", name="uq_incidence_topic_exam"),
        CheckConstraint("weight > 0 and weight <= 1", name="ck_incidence_weight"),
    )


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


DOCUMENT_KINDS = ("grade", "escala", "cursinho", "outro")
DOCUMENT_STATUSES = ("recebido", "extraido", "confirmado", "falhou")
COMMITMENT_KINDS = ("aula", "plantao", "academia", "trabalho", "outro")


class Consent(Base):
    """Consentimento LGPD registrado antes do primeiro upload."""

    __tablename__ = "consent"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(60))
    policy_version: Mapped[str] = mapped_column(String(20))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    """Documento de rotina que o aluno subiu.

    O original vive no object store até a confirmação da semana mais o prazo de
    retenção; depois o expurgo apaga o arquivo e mantém só o JSON extraído.
    """

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="recebido")
    extracted: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"kind in {DOCUMENT_KINDS}", name="ck_document_kind"),
        CheckConstraint(f"status in {DOCUMENT_STATUSES}", name="ck_document_status"),
    )


class Commitment(Base):
    """Compromisso da rotina: aula, plantão, academia, trabalho.

    Tem vigência, porque a rotina muda por rodízio ou escala.
    """

    __tablename__ = "commitment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str] = mapped_column(String(160), default="")
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    on_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint(f"kind in {COMMITMENT_KINDS}", name="ck_commitment_kind"),
        CheckConstraint("(weekday is null) <> (on_day is null)", name="ck_commitment_recurrence"),
        CheckConstraint("duration_minutes > 0", name="ck_commitment_duration"),
    )
