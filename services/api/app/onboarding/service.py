"""O questionário: da resposta do aluno às linhas que o motor precisa.

O aluno escolhe a fase, as provas-alvo e se avalia por grande área. A
autoavaliação da área desce para todos os subtemas dela — a spec prevê refinar
por tema depois.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    TOPIC_LEVEL_AREA,
    TOPIC_LEVEL_SUBTEMA,
    Exam,
    Proficiency,
    Student,
    TargetExam,
    Topic,
)
from ..models import TargetExam as TargetExamRow


class OnboardingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExamInput:
    name: str
    exam_date: date
    is_primary: bool = False


def _descendant_subtopics(session: Session, area_slug: str) -> list[Topic]:
    area = session.scalar(
        select(Topic).where(Topic.slug == area_slug, Topic.level == TOPIC_LEVEL_AREA)
    )
    if area is None:
        raise OnboardingError(f"área desconhecida: {area_slug}")

    temas = list(session.scalars(select(Topic).where(Topic.parent_id == area.id)))
    if not temas:
        return []
    return list(
        session.scalars(
            select(Topic).where(
                Topic.parent_id.in_([t.id for t in temas]),
                Topic.level == TOPIC_LEVEL_SUBTEMA,
            )
        )
    )


def setup_student(
    session: Session,
    student: Student,
    *,
    phase: str,
    mode: str,
    timezone: str,
    weekly_hours: int,
    exams: list[ExamInput],
    self_assessment: dict[str, float],
    exam_slug: str = "enamed",
) -> Student:
    if not exams:
        raise OnboardingError("o aluno precisa de pelo menos uma prova-alvo")
    principais = [e for e in exams if e.is_primary]
    if len(principais) != 1:
        raise OnboardingError("exatamente uma prova precisa ser a principal")
    if weekly_hours <= 0:
        raise OnboardingError("horas por semana precisa ser maior que zero")
    if not self_assessment:
        raise OnboardingError("a autoavaliação por área é obrigatória")
    for area, valor in self_assessment.items():
        if not 0.0 <= valor <= 1.0:
            raise OnboardingError(f"autoavaliação de {area} fora da faixa de 0 a 1")

    # O aluno já existe: entrou pelo link mágico. O questionário só o completa.
    aluno = student
    aluno.phase = phase
    aluno.mode = mode
    aluno.timezone = timezone
    aluno.weekly_hours = weekly_hours
    session.flush()

    # Refazer o questionário substitui as respostas antigas, não soma.
    session.execute(sql_delete(TargetExamRow).where(TargetExamRow.student_id == aluno.id))
    session.execute(sql_delete(Proficiency).where(Proficiency.student_id == aluno.id))
    session.flush()

    prova_do_catalogo = session.scalar(select(Exam).where(Exam.slug == exam_slug))
    for entrada in exams:
        session.add(
            TargetExamRow(
                student_id=aluno.id,
                name=entrada.name,
                exam_date=entrada.exam_date,
                is_primary=entrada.is_primary,
                exam_id=prova_do_catalogo.id if entrada.is_primary and prova_do_catalogo else None,
            )
        )

    for area_slug, valor in self_assessment.items():
        for subtema in _descendant_subtopics(session, area_slug):
            session.add(
                Proficiency(student_id=aluno.id, topic_id=subtema.id, self_assessment=valor)
            )
    session.flush()
    return aluno


def set_primary_exam(session: Session, student: Student, target_exam_id: object) -> TargetExam:
    """Várias provas: o aluno escolhe a principal, e ela define prazo e pesos."""
    alvos = list(
        session.scalars(select(TargetExamRow).where(TargetExamRow.student_id == student.id))
    )
    escolhido = next((a for a in alvos if a.id == target_exam_id), None)
    if escolhido is None:
        raise OnboardingError("prova não é deste aluno")
    for alvo in alvos:
        alvo.is_primary = alvo.id == escolhido.id
    session.flush()
    return escolhido
