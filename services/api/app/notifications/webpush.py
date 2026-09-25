"""Web Push com VAPID.

A biblioteca entra por injeção: o teste passa um dublê e não precisa dela
instalada; em produção, o construtor importa `pywebpush` na primeira chamada.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..config import get_settings
from .base import Message, PushSender, PushTarget, SendFailed, SubscriptionExpired

#: Códigos que o serviço de push devolve quando a assinatura não existe mais.
DEAD_STATUSES = frozenset({404, 410})


def _default_sender() -> Callable[..., Any]:  # pragma: no cover - precisa da lib instalada
    from pywebpush import webpush

    return webpush


class WebPushSender(PushSender):
    def __init__(
        self,
        send: Callable[..., Any] | None = None,
        *,
        private_key: str | None = None,
        subject: str | None = None,
    ) -> None:
        settings = get_settings()
        self._send = send or _default_sender()
        self._private_key = private_key if private_key is not None else settings.vapid_private_key
        self._subject = subject or settings.vapid_subject

    def send(self, target: PushTarget, message: Message) -> None:
        corpo = json.dumps(
            {"title": message.title, "body": message.body, "url": message.url},
            ensure_ascii=False,
        )
        try:
            self._send(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=corpo,
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
            )
        except Exception as erro:  # noqa: BLE001 - a lib levanta tipo próprio
            status = getattr(getattr(erro, "response", None), "status_code", None)
            if status in DEAD_STATUSES:
                raise SubscriptionExpired(str(erro)) from erro
            raise SendFailed(str(erro)) from erro
