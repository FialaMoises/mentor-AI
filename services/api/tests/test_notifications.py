from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.notify import run as run_notify
from app.models import NotificationLog, ProgressEvent, PushSubscription, Student, Task
from app.notifications import (
    Message,
    NullEmailSender,
    NullPushSender,
    PushTarget,
    Senders,
    SendFailed,
    SubscriptionExpired,
    deliver,
    notify_daily_list,
    notify_overflow,
    notify_restart,
)
from app.notifications.webpush import WebPushSender
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

HOJE = date(2026, 9, 25)


class PushQuebrado(NullPushSender):
    def __init__(self, erro: Exception) -> None:
        super().__init__()
        self.erro = erro

    def send(self, target: PushTarget, message: Message) -> None:
        raise self.erro


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


def assina(session: Session, aluno: Student, endpoint: str = "https://push.exemplo/abc") -> None:
    session.add(
        PushSubscription(
            student_id=aluno.id, endpoint=endpoint, p256dh="chave-publica", auth="segredo"
        )
    )
    session.flush()


def test_lista_do_dia_vai_por_push_quando_ha_assinatura(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    senders = Senders.null()

    resultado = notify_daily_list(session, aluno, HOJE, senders)

    assert resultado is not None
    assert (resultado.sent, resultado.channel) == (True, "push")
    assert senders.push.sent[0][1].title == "Sua lista de hoje"  # type: ignore[attr-defined]


def test_lista_do_dia_nao_repete_no_mesmo_dia(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    senders = Senders.null()

    notify_daily_list(session, aluno, HOJE, senders)
    segunda = notify_daily_list(session, aluno, HOJE, senders)

    assert segunda is None
    assert len(senders.push.sent) == 1  # type: ignore[attr-defined]


def test_dia_sem_tarefa_nao_gera_aviso(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    for tarefa in session.scalars(select(Task).where(Task.day == HOJE)):
        session.delete(tarefa)
    session.flush()

    assert notify_daily_list(session, aluno, HOJE, Senders.null()) is None


def test_sem_push_o_aviso_vai_por_email(session: Session, aluno: Student) -> None:
    aluno.email = "aluno@exemplo.com"
    session.flush()
    senders = Senders.null()

    resultado = notify_daily_list(session, aluno, HOJE, senders)

    assert resultado is not None
    assert (resultado.sent, resultado.channel) == (True, "email")
    assert senders.email.sent[0][0] == "aluno@exemplo.com"  # type: ignore[attr-defined]


def test_assinatura_morta_e_marcada_e_cai_para_o_email(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    aluno.email = "aluno@exemplo.com"
    session.flush()
    senders = Senders(push=PushQuebrado(SubscriptionExpired("410")), email=NullEmailSender())

    resultado = notify_daily_list(session, aluno, HOJE, senders)
    session.flush()

    assert resultado is not None
    assert resultado.channel == "email"
    assinatura = session.scalar(select(PushSubscription))
    assert assinatura is not None and assinatura.expired_at is not None


def test_falha_sem_email_fica_registrada_como_nao_entregue(
    session: Session, aluno: Student
) -> None:
    assina(session, aluno)
    aluno.email = None  # sem reserva: a falha tem que aparecer
    session.flush()
    senders = Senders(push=PushQuebrado(SendFailed("timeout")), email=NullEmailSender())

    resultado = deliver(session, aluno, Message(title="t", body="b"), senders)

    assert resultado.sent is False
    assert "timeout" in resultado.detail


def test_aviso_de_estouro_traz_as_opcoes(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    senders = Senders.null()

    notify_overflow(session, aluno, HOJE, 600, 45, senders)

    corpo = senders.push.sent[0][1].body  # type: ignore[attr-defined]
    assert "600 min" in corpo
    assert "45 min por dia" in corpo


def test_aviso_de_estouro_nao_volta_se_a_projecao_quase_nao_mudou(
    session: Session, aluno: Student
) -> None:
    assina(session, aluno)
    senders = Senders.null()

    notify_overflow(session, aluno, HOJE, 600, 45, senders)
    segunda = notify_overflow(session, aluno, HOJE + timedelta(days=1), 620, 46, senders)

    assert segunda is None


def test_aviso_de_estouro_volta_quando_o_buraco_cresce_muito(
    session: Session, aluno: Student
) -> None:
    assina(session, aluno)
    senders = Senders.null()

    notify_overflow(session, aluno, HOJE, 600, 45, senders)
    segunda = notify_overflow(session, aluno, HOJE + timedelta(days=1), 1200, 90, senders)

    assert segunda is not None


def test_plano_que_cabe_nao_avisa_nada(session: Session, aluno: Student) -> None:
    assina(session, aluno)

    assert notify_overflow(session, aluno, HOJE, 0, 0, Senders.null()) is None


def test_convite_de_recomeco_nao_cobra(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    senders = Senders.null()

    notify_restart(session, aluno, HOJE, senders)

    mensagem = senders.push.sent[0][1]  # type: ignore[attr-defined]
    assert "metade da carga" in mensagem.body
    assert "atras" not in mensagem.body.lower()


def test_job_de_notificacao_manda_a_lista_do_dia(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    senders = Senders.null()

    resumos = run_notify(session, senders, today_for=lambda _tz: HOJE)
    session.flush()

    assert len(resumos) == 1
    assert "lista do dia" in resumos[0]
    assert list(session.scalars(select(NotificationLog)))


def test_job_convida_ao_recomeco_quem_sumiu(session: Session, aluno: Student) -> None:
    assina(session, aluno)
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None
    session.add(
        ProgressEvent(
            task_id=tarefa.id,
            action="feita",
            occurred_at=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )
    session.flush()

    resumos = run_notify(session, Senders.null(), today_for=lambda _tz: HOJE)

    assert "recomeço" in resumos[0]


def test_webpush_traduz_assinatura_morta(session: Session) -> None:
    class Resposta:
        status_code = 410

    class ErroDaLib(Exception):
        response = Resposta()

    def envio_que_falha(**_kwargs: object) -> None:
        raise ErroDaLib()

    sender = WebPushSender(envio_que_falha, private_key="chave", subject="mailto:a@b.c")

    with pytest.raises(SubscriptionExpired):
        sender.send(PushTarget("https://push", "p", "a"), Message(title="t", body="b"))


def test_webpush_envia_o_payload_com_titulo_e_corpo() -> None:
    enviados: list[dict[str, object]] = []

    def envio(**kwargs: object) -> None:
        enviados.append(kwargs)

    sender = WebPushSender(envio, private_key="chave", subject="mailto:a@b.c")
    sender.send(PushTarget("https://push", "p", "a"), Message(title="Oi", body="Corpo"))

    assert enviados[0]["subscription_info"] == {
        "endpoint": "https://push",
        "keys": {"p256dh": "p", "auth": "a"},
    }
    assert "Oi" in str(enviados[0]["data"])
