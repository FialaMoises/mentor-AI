"""Dependências que o teste troca: o object store e o provedor de extração."""

from __future__ import annotations

from .extraction.provider import ExtractionProvider, get_provider
from .notifications import EmailSender, NullEmailSender, NullPushSender, PushSender, Senders
from .storage import ObjectStore


def get_object_store() -> ObjectStore:
    from .storage.s3 import get_store

    return get_store()


def get_extraction_provider() -> ExtractionProvider:
    return get_provider()


def get_senders() -> Senders:
    """Sem chave VAPID ou SMTP configurados, nada sai daqui — e isso é proposital."""
    from .config import get_settings

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
