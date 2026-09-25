"""Assinaturas Web Push e sincronização da fila offline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..deps import current_student
from ..models import PushSubscription, Student
from ..progress import ProgressEntry, sync

router = APIRouter(prefix="/api/v1")


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=600)
    keys: PushKeys


class PushConfigOut(BaseModel):
    public_key: str
    enabled: bool


class ProgressEntryIn(BaseModel):
    task_id: uuid.UUID
    action: Literal["feita", "nao_deu"]
    answered: int | None = Field(default=None, ge=0, le=1000)
    correct: int | None = Field(default=None, ge=0, le=1000)
    client_event_id: uuid.UUID
    occurred_at: datetime | None = None


class SyncIn(BaseModel):
    entries: list[ProgressEntryIn] = Field(max_length=200)


class SyncOut(BaseModel):
    applied: int
    duplicates: int
    unknown: int


@router.get("/push/config", response_model=PushConfigOut)
def get_push_config() -> PushConfigOut:
    """A chave pública que o navegador precisa para assinar."""
    settings = get_settings()
    return PushConfigOut(
        public_key=settings.vapid_public_key, enabled=bool(settings.vapid_public_key)
    )


@router.post("/me/push-subscriptions", status_code=status.HTTP_201_CREATED)
def post_subscription(
    payload: PushSubscriptionIn,
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    assinatura = session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
    )
    if assinatura is None:
        assinatura = PushSubscription(student_id=aluno.id, endpoint=payload.endpoint)
        session.add(assinatura)
    assinatura.student_id = aluno.id
    assinatura.p256dh = payload.keys.p256dh
    assinatura.auth = payload.keys.auth
    assinatura.expired_at = None
    session.flush()
    return {"status": "assinado"}


@router.delete("/me/push-subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def delete_subscription(
    endpoint: str,
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    assinatura = session.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.student_id == aluno.id
        )
    )
    if assinatura is not None:
        session.delete(assinatura)
        session.flush()


@router.post("/me/progress/sync", response_model=SyncOut)
def post_sync(
    payload: SyncIn,
    aluno: Annotated[Student, Depends(current_student)],
    session: Annotated[Session, Depends(get_session)],
) -> SyncOut:
    """A fila que o navegador acumulou offline. Reenviar a mesma fila é seguro."""
    resultado = sync(
        session,
        aluno,
        [
            ProgressEntry(
                task_id=e.task_id,
                action=e.action,
                answered=e.answered,
                correct=e.correct,
                client_event_id=e.client_event_id,
                occurred_at=e.occurred_at,
            )
            for e in payload.entries
        ],
    )
    return SyncOut(
        applied=resultado.applied,
        duplicates=resultado.duplicates,
        unknown=resultado.unknown,
    )
