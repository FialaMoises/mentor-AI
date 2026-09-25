"""Quem decide o que avisar, para quem, e quantas vezes.

Push primeiro; e-mail só quando o aluno não tem assinatura viva — é a reserva
do iPhone sem app instalado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NotificationLog, PushSubscription, Student, Task
from .base import (
    EmailSender,
    Message,
    NullEmailSender,
    NullPushSender,
    PushSender,
    PushTarget,
    SendFailed,
    SubscriptionExpired,
)

DAILY_LIST = "lista_do_dia"
OVERFLOW = "aviso_de_estouro"
RESTART = "recomeco"

#: O aviso de estouro só volta quando o buraco muda bastante.
OVERFLOW_CHANGE_THRESHOLD = 0.25


@dataclass(frozen=True, slots=True)
class Senders:
    push: PushSender
    email: EmailSender

    @classmethod
    def null(cls) -> Senders:
        return cls(push=NullPushSender(), email=NullEmailSender())


@dataclass(frozen=True, slots=True)
class SendOutcome:
    sent: bool
    channel: str
    detail: str = ""


def already_sent(session: Session, student: Student, kind: str, day: date) -> bool:
    return (
        session.scalar(
            select(NotificationLog.id).where(
                NotificationLog.student_id == student.id,
                NotificationLog.kind == kind,
                NotificationLog.day == day,
            )
        )
        is not None
    )


def live_subscriptions(session: Session, student: Student) -> list[PushSubscription]:
    return list(
        session.scalars(
            select(PushSubscription).where(
                PushSubscription.student_id == student.id,
                PushSubscription.expired_at.is_(None),
            )
        )
    )


def deliver(
    session: Session,
    student: Student,
    message: Message,
    senders: Senders,
) -> SendOutcome:
    """Tenta o push em cada assinatura viva; se nenhuma entregar, vai de e-mail."""
    assinaturas = live_subscriptions(session, student)
    erro_push = ""

    for assinatura in assinaturas:
        alvo = PushTarget(
            endpoint=assinatura.endpoint, p256dh=assinatura.p256dh, auth=assinatura.auth
        )
        try:
            senders.push.send(alvo, message)
            return SendOutcome(sent=True, channel="push")
        except SubscriptionExpired as erro:
            assinatura.expired_at = datetime.now(UTC)
            erro_push = str(erro)
        except SendFailed as erro:
            erro_push = str(erro)
    session.flush()

    if student.email:
        try:
            senders.email.send(student.email, message)
            return SendOutcome(sent=True, channel="email")
        except SendFailed as erro:
            return SendOutcome(sent=False, channel="email", detail=str(erro)[:300])

    detalhe = erro_push or "aluno sem assinatura de push e sem e-mail"
    return SendOutcome(sent=False, channel="push", detail=detalhe[:300])


def _log(
    session: Session, student: Student, kind: str, day: date, outcome: SendOutcome
) -> NotificationLog:
    registro = NotificationLog(
        student_id=student.id,
        kind=kind,
        channel=outcome.channel,
        day=day,
        delivered=outcome.sent,
        detail=outcome.detail,
    )
    session.add(registro)
    session.flush()
    return registro


def notify_daily_list(
    session: Session, student: Student, today: date, senders: Senders
) -> SendOutcome | None:
    """A lista do dia. Nada de aviso quando o dia está vazio."""
    if already_sent(session, student, DAILY_LIST, today):
        return None

    tarefas = list(
        session.scalars(
            select(Task).where(
                Task.student_id == student.id, Task.day == today, Task.status == "pendente"
            )
        )
    )
    if not tarefas:
        return None

    minutos = sum(t.minutes for t in tarefas)
    mensagem = Message(
        title="Sua lista de hoje",
        body=f"{len(tarefas)} tarefas, {minutos} min. Bom estudo.",
    )
    resultado = deliver(session, student, mensagem, senders)
    _log(session, student, DAILY_LIST, today, resultado)
    return resultado


def notify_overflow(
    session: Session,
    student: Student,
    today: date,
    missing_minutes: int,
    extra_per_day: int,
    senders: Senders,
) -> SendOutcome | None:
    """Aviso de estouro, com as opções calculadas. Só volta se a projeção mudar bastante."""
    if missing_minutes <= 0:
        return None
    if already_sent(session, student, OVERFLOW, today):
        return None

    ultimo = session.scalar(
        select(NotificationLog)
        .where(NotificationLog.student_id == student.id, NotificationLog.kind == OVERFLOW)
        .order_by(NotificationLog.day.desc())
    )
    if ultimo is not None and ultimo.detail.isdigit():
        anterior = int(ultimo.detail)
        if anterior > 0 and abs(missing_minutes - anterior) / anterior < OVERFLOW_CHANGE_THRESHOLD:
            return None

    mensagem = Message(
        title="O plano não cabe até a prova",
        body=(
            f"Faltam {missing_minutes} min. Dá para somar {extra_per_day} min por dia "
            "ou cortar os temas de menor peso — você decide."
        ),
        url="/hoje",
    )
    resultado = deliver(session, student, mensagem, senders)
    registro = _log(session, student, OVERFLOW, today, resultado)
    registro.detail = str(missing_minutes)
    session.flush()
    return resultado


def notify_restart(
    session: Session, student: Student, today: date, senders: Senders
) -> SendOutcome | None:
    """Convite de recomeço, sem tom de cobrança."""
    if already_sent(session, student, RESTART, today):
        return None

    mensagem = Message(
        title="Que tal recomeçar leve?",
        body="Preparei uma semana com metade da carga para você voltar sem susto.",
    )
    resultado = deliver(session, student, mensagem, senders)
    _log(session, student, RESTART, today, resultado)
    return resultado
