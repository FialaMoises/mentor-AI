"""Dependências da API: sessão do aluno, guarda de admin, e o que o teste troca."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .auth import student_for_token
from .billing import BillingGateway, FakeGateway
from .config import get_settings
from .db import get_session
from .extraction.provider import ExtractionProvider, get_provider
from .models import Student
from .notifications import EmailSender, NullEmailSender, NullPushSender, PushSender, Senders
from .storage import ObjectStore


def get_object_store() -> ObjectStore:
    from .storage.s3 import get_store

    return get_store()


def get_extraction_provider() -> ExtractionProvider:
    return get_provider()


def get_senders() -> Senders:
    """Sem chave VAPID ou SMTP configurados, nada sai daqui — e isso é proposital."""
    settings = get_settings()
    push: PushSender = NullPushSender()
    email: EmailSender = NullEmailSender()

    if settings.vapid_private_key:
        from .notifications.webpush import WebPushSender

        push = WebPushSender()
    if settings.smtp_host:
        from .notifications.email import SmtpEmailSender

        email = SmtpEmailSender()
    return Senders(push=push, email=email)


def get_gateway() -> BillingGateway:
    """Enquanto não há provedor real configurado, o gateway de mentira."""
    return FakeGateway(secret=get_settings().billing_webhook_secret or "segredo-de-teste")


def current_student(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Student:
    """O aluno da sessão. Nenhuma rota de dado pessoal existe sem isto."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "faça login para continuar",
            headers={"WWW-Authenticate": "Bearer"},
        )

    aluno = student_for_token(session, authorization.split(" ", 1)[1].strip())
    if aluno is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "sessão expirada",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return aluno


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    """O painel do piloto. Sem token configurado, ninguém entra."""
    esperado = get_settings().admin_token
    if not esperado or not x_admin_token or not hmac.compare_digest(x_admin_token, esperado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "painel restrito")
