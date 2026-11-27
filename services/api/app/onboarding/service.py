"""O questionário: da resposta do aluno às linhas que o motor precisa.

O aluno escolhe a fase, as provas-alvo e se avalia por grande área. A
autoavaliação da área desce para todos os subtemas dela — a spec prevê refinar
por tema depois.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    TOPIC_LEVEL_AREA,
    TOPIC_LEVEL_SUBTEMA,
    Document,
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
    today: date,
    exam_slug: str = "enamed",
) -> Student:
    if not exams:
        raise OnboardingError("o aluno precisa de pelo menos uma prova-alvo")
    principais = [e for e in exams if e.is_primary]
    if len(principais) != 1:
        raise OnboardingError("exatamente uma prova precisa ser a principal")
    if principais[0].exam_date <= today:
        raise OnboardingError("a data da prova principal precisa ser de amanhã em diante")
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

    _replace_exams(session, aluno, exams, exam_slug)
    _replace_self_assessment(session, aluno, self_assessment)
    session.flush()
    return aluno


def _exams_from_documents(session: Session, student: Student) -> set[tuple[str, date]]:
    """As provas que vieram de um arquivo confirmado: não são do questionário."""
    chaves: set[tuple[str, date]] = set()
    for extraido in session.scalars(
        select(Document.extracted).where(
            Document.student_id == student.id, Document.status == "confirmado"
        )
    ):
        provas = extraido.get("exams", []) if isinstance(extraido, dict) else []
        for prova in provas if isinstance(provas, list) else []:
            try:
                chaves.add((str(prova["name"]), date.fromisoformat(str(prova["exam_date"]))))
            except (KeyError, TypeError, ValueError):
                continue
    return chaves


def _replace_exams(
    session: Session, student: Student, exams: list[ExamInput], exam_slug: str
) -> None:
    """Refazer o questionário troca as provas dele e deixa as que vieram de arquivo."""
    do_arquivo = _exams_from_documents(session, student)
    atuais = list(
        session.scalars(select(TargetExamRow).where(TargetExamRow.student_id == student.id))
    )
    restantes: dict[tuple[str, date], TargetExamRow] = {}
    for linha in atuais:
        if (linha.name, linha.exam_date) in do_arquivo:
            linha.is_primary = False
            restantes[(linha.name, linha.exam_date)] = linha
        else:
            session.delete(linha)
    session.flush()

    prova_do_catalogo = session.scalar(select(Exam).where(Exam.slug == exam_slug))
    for entrada in exams:
        alvo = restantes.get((entrada.name, entrada.exam_date))
        if alvo is None:
            alvo = TargetExamRow(
                student_id=student.id, name=entrada.name, exam_date=entrada.exam_date
            )
            session.add(alvo)
        alvo.is_primary = entrada.is_primary
        alvo.exam_id = prova_do_catalogo.id if entrada.is_primary and prova_do_catalogo else None
    session.flush()


def _replace_self_assessment(
    session: Session, student: Student, self_assessment: dict[str, float]
) -> None:
    """Troca a autoavaliação sem perder o que o aluno já lançou de questões.

    `answered`/`correct` são histórico: nunca voltam a zero por causa do questionário.
    Subtema sem lançamento e fora das áreas respondidas sai, como antes.
    """
    atuais = {
        linha.topic_id: linha
        for linha in session.scalars(
            select(Proficiency).where(Proficiency.student_id == student.id)
        )
    }
    avaliados: set[object] = set()
    for area_slug, valor in self_assessment.items():
        for subtema in _descendant_subtopics(session, area_slug):
            avaliados.add(subtema.id)
            linha = atuais.get(subtema.id)
            if linha is None:
                session.add(
                    Proficiency(student_id=student.id, topic_id=subtema.id, self_assessment=valor)
                )
            else:
                linha.self_assessment = valor
    for topic_id, linha in atuais.items():
        if topic_id not in avaliados and not linha.answered:
            session.delete(linha)


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
