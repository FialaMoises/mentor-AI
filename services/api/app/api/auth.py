"""Entrada por link mágico, saída, e a conta do aluno (exportar e apagar)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import AuthError, logout, request_login, revoke_all, verify_login
from ..billing import start_trial, subscription_of
from ..clock import monotonic, today_in
from ..config import get_settings
from ..db import get_session
from ..deps import current_student, get_object_store, get_senders
from ..documents import erase as erase_document
from ..models import Commitment, Document, Proficiency, Student, TargetExam, Task
from ..notifications import Message, Senders
from ..ratelimit import get_rate_limiter, retry_after
from ..storage import ObjectStore

router = APIRouter(prefix="/api/v1")


class LoginRequestIn(BaseModel):
    email: EmailStr


class LoginVerifyIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    student_id: str
    needs_onboarding: bool


class MeOut(BaseModel):
    id: str
    email: str | None
    phase: str
    mode: str
    weekly_hours: int
    needs_onboarding: bool
    subscription_status: str
    trial_ends_on: date | None


def _needs_onboarding(session: Session, student: Student) -> bool:
    """Sem prova principal, o aluno ainda não terminou o questionário."""
    return (
        session.scalar(
            select(TargetExam.id).where(
                TargetExam.student_id == student.id, TargetExam.is_primary.is_(True)
            )
        )
        is None
    )


@router.post("/auth/magic-link", status_code=status.HTTP_202_ACCEPTED)
def post_magic_link(
    payload: LoginRequestIn,
    session: Annotated[Session, Depends(get_session)],
    senders: Annotated[Senders, Depends(get_senders)],
) -> dict[str, str]:
    """Manda o link. A resposta é a mesma para e-mail conhecido ou não."""
    settings = get_settings()
    espera = get_rate_limiter().hit(
        "login:" + str(payload.email).strip().lower(),
        limit=settings.rate_limit_login_per_window,
        window_seconds=settings.rate_limit_login_window_minutes * 60,
        now=monotonic(),
    )
    if espera is not None:
        raise HTTPException(
            429,
            f"muitos links pedidos para este e-mail; tente de novo em {retry_after(espera)} s",
            headers={"Retry-After": retry_after(espera)},
        )
    try:
        link = request_login(session, str(payload.email))
    except AuthError as erro:
        raise HTTPException(422, str(erro)) from erro

    senders.email.send(
        str(payload.email),
        Message(
            title="Seu link de entrada no mentor-AI",
            body="Toque no link abaixo. Vale por 20 minutos e serve uma vez só.",
            url=link.url(settings.app_base_url),
        ),
    )
    return {"status": "enviado"}


@router.post("/auth/verify", response_model=SessionOut)
def post_verify(
    payload: LoginVerifyIn, session: Annotated[Session, Depends(get_session)]
) -> SessionOut:
    try:
        entrada = verify_login(session, payload.token)
    except AuthError as erro:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(erro)) from erro

    start_trial(session, entrada.student, today_in(entrada.student.timezone))
    return SessionOut(
        token=entrada.token,
        expires_at=entrada.expires_at,
        student_id=str(entrada.student.id),
        needs_onboarding=_needs_onboarding(session, entrada.student),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def post_logout(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization and authorization.lower().startswith("bearer "):
        logout(session, authorization.split(" ", 1)[1].strip())


@router.get("/me", response_model=MeOut)
def get_me(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> MeOut:
    assinatura = subscription_of(session, student)
    return MeOut(
        id=str(student.id),
        email=student.email,
        phase=student.phase,
        mode=student.mode,
        weekly_hours=student.weekly_hours,
        needs_onboarding=_needs_onboarding(session, student),
        subscription_status=assinatura.status if assinatura else "trial",
        trial_ends_on=assinatura.trial_ends_on if assinatura else None,
    )


@router.get("/me/export")
def get_export(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    """LGPD: tudo o que guardamos sobre o aluno, em JSON."""
    tarefas = list(session.scalars(select(Task).where(Task.student_id == student.id)))
    return {
        "aluno": {
            "id": str(student.id),
            "email": student.email,
            "fase": student.phase,
            "modo": student.mode,
            "horas_por_semana": student.weekly_hours,
            "fuso": student.timezone,
            "criado_em": student.created_at.isoformat(),
        },
        "provas": [
            {"nome": p.name, "data": p.exam_date.isoformat(), "principal": p.is_primary}
            for p in session.scalars(select(TargetExam).where(TargetExam.student_id == student.id))
        ],
        "compromissos": [
            {
                "tipo": c.kind,
                "descricao": c.label,
                "dia_da_semana": c.weekday,
                "data": c.on_day.isoformat() if c.on_day else None,
                "duracao_min": c.duration_minutes,
                "inicio": c.starts_at.strftime("%H:%M") if c.starts_at else None,
                "origem": "arquivo" if c.document_id else "manual",
                "vigencia_inicio": c.starts_on.isoformat() if c.starts_on else None,
                "vigencia_fim": c.ends_on.isoformat() if c.ends_on else None,
                "editado_pelo_aluno": c.edited_by_student,
                "serie": str(c.series_id) if c.series_id else None,
            }
            for c in session.scalars(select(Commitment).where(Commitment.student_id == student.id))
        ],
        "documentos": [
            {
                "tipo": d.kind,
                "arquivo": d.original_name,
                "status": d.status,
                "extraido": d.extracted,
                "original_ainda_guardado": d.storage_key is not None,
            }
            for d in session.scalars(select(Document).where(Document.student_id == student.id))
        ],
        "proficiencias": [
            {
                "tema": p.topic_id and str(p.topic_id),
                "autoavaliacao": p.self_assessment,
                "questoes": p.answered,
                "acertos": p.correct,
            }
            for p in session.scalars(
                select(Proficiency).where(Proficiency.student_id == student.id)
            )
        ],
        "tarefas": [
            {
                "dia": t.day.isoformat(),
                "tipo": t.kind,
                "minutos": t.minutes,
                "status": t.status,
            }
            for t in tarefas
        ],
    }


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    student: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> None:
    """LGPD: apaga a conta, os arquivos e tudo que pende dela."""
    for documento in session.scalars(select(Document).where(Document.student_id == student.id)):
        erase_document(session, documento, store)
    revoke_all(session, student)
    session.delete(student)
    session.flush()
