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
from ..deps import current_student
from ..documents import POLICY_VERSION, has_consent, record_consent
from ..models import Proficiency, Student
from ..onboarding import ExamInput, OnboardingError, set_primary_exam, setup_student

#: O nome da constante mudou entre versões do Starlette; o número, não.
UNPROCESSABLE = 422

router = APIRouter(prefix="/api/v1")


class ExamIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    exam_date: date
    is_primary: bool = False


class ProfileIn(BaseModel):
    phase: Literal["faculdade", "formado"]
    mode: Literal["cursinho", "independente"]
    timezone: str = Field(default="America/Fortaleza", max_length=64)
    weekly_hours: int = Field(ge=1, le=100)
    exams: list[ExamIn] = Field(min_length=1, max_length=10)
    #: slug da área do catálogo → autoavaliação de 0 a 1.
    self_assessment: dict[str, float] = Field(min_length=1)


class ProfileOut(BaseModel):
    id: uuid.UUID
    phase: str
    mode: str
    weekly_hours: int
    topics_assessed: int
    consent_required: bool


class ConsentOut(BaseModel):
    accepted: bool
    policy_version: str


@router.put("/me/profile", response_model=ProfileOut)
def put_profile(
    payload: ProfileIn,
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> ProfileOut:
    """O questionário preenche o aluno que já entrou pelo link mágico."""
    try:
        setup_student(
            session,
            aluno,
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
    return ProfileOut(
        id=aluno.id,
        phase=aluno.phase,
        mode=aluno.mode,
        weekly_hours=aluno.weekly_hours,
        topics_assessed=avaliados or 0,
        consent_required=not has_consent(session, aluno),
    )


@router.post("/me/consent", response_model=ConsentOut)
def post_consent(
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> ConsentOut:
    """O aluno aceita o aviso de privacidade. Sem isto, upload nenhum passa."""
    if not has_consent(session, aluno):
        record_consent(session, aluno)
    return ConsentOut(accepted=True, policy_version=POLICY_VERSION)


@router.post("/me/exams/{target_exam_id}/primary", response_model=dict)
def post_primary_exam(
    target_exam_id: uuid.UUID,
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    try:
        alvo = set_primary_exam(session, aluno, target_exam_id)
    except OnboardingError as erro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(erro)) from erro
    return {"primary_exam": alvo.name, "exam_date": alvo.exam_date.isoformat()}
