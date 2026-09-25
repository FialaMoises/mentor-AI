"""Portas de envio: push no navegador, e-mail como reserva."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
    """Quando não há chave VAPID configurada: registra e segue a vida."""

    def __init__(self) -> None:
        self.sent: list[tuple[PushTarget, Message]] = []

    def send(self, target: PushTarget, message: Message) -> None:
        self.sent.append((target, message))


class NullEmailSender(EmailSender):
    def __init__(self) -> None:
        self.sent: list[tuple[str, Message]] = []

    def send(self, to: str, message: Message) -> None:
        self.sent.append((to, message))
