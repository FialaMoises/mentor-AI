"""Portas de envio: push no navegador, e-mail como reserva."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("mentor.notifications")


class SubscriptionExpired(RuntimeError):
    """O navegador disse que a assinatura morreu. Não insista nela."""


class SendFailed(RuntimeError):
    """Falha temporária: vale tentar de novo amanhã."""


@dataclass(frozen=True, slots=True)
class Message:
    title: str
    body: str
    url: str = "/hoje"


@dataclass(frozen=True, slots=True)
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


class PushSender(Protocol):
    def send(self, target: PushTarget, message: Message) -> None: ...


class EmailSender(Protocol):
    def send(self, to: str, message: Message) -> None: ...


class NullPushSender(PushSender):
    """Sem chave VAPID: registra a intenção, não envia, e segue a vida."""

    def __init__(self) -> None:
        self.sent: list[tuple[PushTarget, Message]] = []

    def send(self, target: PushTarget, message: Message) -> None:
        self.sent.append((target, message))


class NullEmailSender(EmailSender):
    """Sem SMTP: a mensagem vai para o log, com a URL inteira.

    É o que torna o desenvolvimento possível — o link mágico de entrada aparece
    em `docker compose logs api`. Em produção, configure o SMTP: com ele, esta
    classe não é usada e nenhum link de entrada chega perto de um arquivo de log.
    """

    def __init__(self, echo: bool = True) -> None:
        self.sent: list[tuple[str, Message]] = []
        self.echo = echo

    def send(self, to: str, message: Message) -> None:
        self.sent.append((to, message))
        if self.echo:
            logger.warning(
                "SMTP não configurado — e-mail para %s não foi enviado.\n  %s\n  %s\n  %s",
                to,
                message.title,
                message.body,
                message.url,
            )
