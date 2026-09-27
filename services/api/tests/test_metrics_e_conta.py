from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import start_trial
from app.clock import today_in
from app.config import get_settings
from app.metrics import collect
from app.models import Document, PlanVersion, ProgressEvent, Student, Task
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed
from app.storage import InMemoryStore

#: O relógio anda: a rota lê o dia de hoje de verdade, então o seed usa o mesmo dia.
HOJE = today_in(get_settings().default_timezone)


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.flush()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    # A conta nasceu há um mês: já passou da semana 3.
    student.created_at = datetime(2026, 8, 25, tzinfo=UTC)
    session.flush()
    return student


@pytest.fixture
def admin(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_TOKEN", "token-do-painel")
    yield {"x-admin-token": "token-do-painel"}
    get_settings.cache_clear()


def marca(session: Session, tarefa: Task, quando: datetime, **extras: object) -> None:
    tarefa.status = "feita"
    session.add(ProgressEvent(task_id=tarefa.id, action="feita", occurred_at=quando, **extras))  # type: ignore[arg-type]
    session.flush()


def test_sem_aluno_os_numeros_vem_zerados(session: Session) -> None:
    numeros = collect(session, HOJE)

    assert numeros.students == 0
    assert numeros.retention_week_three == 0.0


def test_quem_marcou_na_semana_tres_conta_como_ativo(session: Session, aluno: Student) -> None:
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None
    # 16 dias depois da criação da conta: dentro da janela da semana 3.
    marca(session, tarefa, datetime(2026, 9, 10, tzinfo=UTC))

    numeros = collect(session, HOJE)

    assert numeros.reached_week_three == 1
    assert numeros.active_week_three == 1
    assert numeros.retention_week_three == 1.0


def test_quem_sumiu_antes_da_semana_tres_nao_conta_como_ativo(
    session: Session, aluno: Student
) -> None:
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None
    # Dois dias depois de criar a conta: fora da janela.
    marca(session, tarefa, datetime(2026, 8, 27, tzinfo=UTC))

    numeros = collect(session, HOJE)

    assert numeros.reached_week_three == 1
    assert numeros.active_week_three == 0


def test_tarefas_feitas_na_ultima_semana(session: Session, aluno: Student) -> None:
    tarefas = list(session.scalars(select(Task).where(Task.day == HOJE)))[:2]
    for tarefa in tarefas:
        marca(session, tarefa, datetime(2026, 9, 25, tzinfo=UTC))

    numeros = collect(session, HOJE)

    assert numeros.tasks_done_last_week == 2


def test_tempo_ate_o_primeiro_plano_sai_em_minutos(session: Session, aluno: Student) -> None:
    versao = session.scalars(select(PlanVersion)).first()
    assert versao is not None
    versao.created_at = aluno.created_at + timedelta(minutes=7)
    session.flush()

    numeros = collect(session, HOJE)

    assert numeros.median_minutes_to_first_plan == pytest.approx(7.0, abs=0.1)


def test_quem_lanca_acertos_e_contado(session: Session, aluno: Student) -> None:
    tarefa = session.scalars(select(Task).where(Task.kind == "questoes")).first()
    assert tarefa is not None
    marca(session, tarefa, datetime(2026, 9, 25, tzinfo=UTC), answered=20, correct=15)

    numeros = collect(session, HOJE)

    assert numeros.students_logging_answers == 1
    assert numeros.answer_logging_rate == 1.0


def test_quebra_por_status_de_assinatura(session: Session, aluno: Student) -> None:
    start_trial(session, aluno, HOJE)
    session.flush()

    numeros = collect(session, HOJE)

    assert numeros.by_subscription_status == {"trial": 1}


def test_painel_sem_token_nao_abre(client: TestClient, session: Session, aluno: Student) -> None:
    session.commit()

    assert client.get("/api/v1/admin/metrics").status_code == 403


def test_painel_com_token_errado_nao_abre(
    client: TestClient, session: Session, aluno: Student, admin: dict[str, str]
) -> None:
    session.commit()

    assert (
        client.get("/api/v1/admin/metrics", headers={"x-admin-token": "chute"}).status_code == 403
    )


def test_painel_devolve_os_numeros(
    client: TestClient, session: Session, aluno: Student, admin: dict[str, str]
) -> None:
    session.commit()

    corpo = client.get("/api/v1/admin/metrics", headers=admin).json()

    assert corpo["students"] == 1
    assert "retention_week_three" in corpo


def test_painel_exporta_csv(
    client: TestClient, session: Session, aluno: Student, admin: dict[str, str]
) -> None:
    session.commit()

    resposta = client.get("/api/v1/admin/metrics.csv", headers=admin)

    assert resposta.status_code == 200
    assert "text/csv" in resposta.headers["content-type"]
    assert "students" in resposta.text


def test_aluno_exporta_os_proprios_dados(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    session.commit()

    corpo = client.get("/api/v1/me/export", headers=login(aluno)).json()

    assert corpo["aluno"]["id"] == str(aluno.id)
    assert corpo["provas"]
    assert corpo["tarefas"]


def test_exportacao_exige_sessao(client: TestClient, session: Session, aluno: Student) -> None:
    session.commit()

    assert client.get("/api/v1/me/export").status_code == 401


def test_apagar_a_conta_leva_tudo_junto(
    client: TestClient,
    session: Session,
    aluno: Student,
    api_store: InMemoryStore,
    login,  # type: ignore[no-untyped-def]
) -> None:
    session.add(
        Document(
            student_id=aluno.id,
            kind="grade",
            original_name="grade.pdf",
            storage_key="chave",
            content_type="application/pdf",
            size_bytes=10,
        )
    )
    api_store.put("chave", b"conteudo", "application/pdf")
    session.commit()
    cabecalho = login(aluno)

    assert client.delete("/api/v1/me", headers=cabecalho).status_code == 204

    assert session.get(Student, aluno.id) is None
    assert not list(session.scalars(select(Task)))
    assert len(api_store) == 0
    assert client.get("/api/v1/me", headers=cabecalho).status_code == 401
