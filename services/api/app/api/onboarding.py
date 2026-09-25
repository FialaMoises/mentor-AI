"""Questionário, consentimento e escolha da prova principal."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..documents import POLICY_VERSION, has_consent, record_consent
from ..models import Proficiency, Student
from ..onboarding import ExamInput, OnboardingError, create_student, set_primary_exam

#: O nome da constante mudou entre versões do Starlette; o número, não.
UNPROCESSABLE = 422

router = APIRouter(prefix="/api/v1")


class ExamIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    exam_date: date
    is_primary: bool = False


class StudentIn(BaseModel):
    phase: Literal["faculdade", "formado"]
    mode: Literal["cursinho", "independente"]
    timezone: str = Field(default="America/Fortaleza", max_length=64)
    weekly_hours: int = Field(ge=1, le=100)
    exams: list[ExamIn] = Field(min_length=1, max_length=10)
    #: slug da área do catálogo → autoavaliação de 0 a 1.
    self_assessment: dict[str, float] = Field(min_length=1)


class StudentOut(BaseModel):
    id: uuid.UUID
    phase: str
    mode: str
    weekly_hours: int
    topics_assessed: int
    consent_required: bool


class ConsentOut(BaseModel):
    accepted: bool
    policy_version: str


def _student(student_id: uuid.UUID, session: Session) -> Student:
    aluno = session.get(Student, student_id)
    if aluno is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "aluno não encontrado")
    return aluno


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def post_student(
    payload: StudentIn, session: Annotated[Session, Depends(get_session)]
) -> StudentOut:
    try:
        aluno = create_student(
            session,
            phase=payload.phase,
            mode=payload.mode,
            timezone=payload.timezone,
            weekly_hours=payload.weekly_hours,
            exams=[
                ExamInput(name=e.name, exam_date=e.exam_date, is_primary=e.is_primary)
                for e in payload.exams
            ],
            self_assessment=payload.self_assessment,
        )
    except OnboardingError as erro:
        raise HTTPException(UNPROCESSABLE, str(erro)) from erro

    avaliados = session.scalar(
        select(func.count()).select_from(Proficiency).where(Proficiency.student_id == aluno.id)
    )
    return StudentOut(
        id=aluno.id,
        phase=aluno.phase,
        mode=aluno.mode,
        weekly_hours=aluno.weekly_hours,
        topics_assessed=avaliados or 0,
        consent_required=not has_consent(session, aluno),
    )


@router.post("/students/{student_id}/consent", response_model=ConsentOut)
def post_consent(
    student_id: uuid.UUID, session: Annotated[Session, Depends(get_session)]
) -> ConsentOut:
    """O aluno aceita o aviso de privacidade. Sem isto, upload nenhum passa."""
    aluno = _student(student_id, session)
    if not has_consent(session, aluno):
        record_consent(session, aluno)
    return ConsentOut(accepted=True, policy_version=POLICY_VERSION)


@router.post("/students/{student_id}/exams/{target_exam_id}/primary", response_model=dict)
def post_primary_exam(
    student_id: uuid.UUID,
    target_exam_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    aluno = _student(student_id, session)
    try:
        alvo = set_primary_exam(session, aluno, target_exam_id)
    except OnboardingError as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    return {"primary_exam": alvo.name, "exam_date": alvo.exam_date.isoformat()}
