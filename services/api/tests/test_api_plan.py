from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import today_in
from app.config import get_settings
from app.models import Proficiency, ProgressEvent, Student, Task
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

#: O relógio anda: a rota lê o dia de hoje de verdade, então o seed usa o mesmo dia.
HOJE = today_in(get_settings().default_timezone)


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    session.commit()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_plano_do_dia_exige_sessao(client: TestClient, aluno: Student) -> None:
    assert client.get("/api/v1/me/plan/today").status_code == 401


def test_token_invalido_e_recusado(client: TestClient, aluno: Student) -> None:
    resposta = client.get(
        "/api/v1/me/plan/today", headers={"Authorization": "Bearer nao-sou-um-token"}
    )
    assert resposta.status_code == 401


def test_lista_do_dia_traz_as_tarefas_do_seed(client: TestClient, aluno: Student, login) -> None:  # type: ignore[no-untyped-def]
    resposta = client.get("/api/v1/me/plan/today", headers=login(aluno))
    corpo = resposta.json()

    assert resposta.status_code == 200
    assert corpo["capacity_minutes"] == 180
    assert len(corpo["tasks"]) > 0
    assert sum(t["minutes"] for t in corpo["tasks"]) <= corpo["capacity_minutes"]
    assert {t["status"] for t in corpo["tasks"]} == {"pendente"}


def test_marcar_feito_muda_o_status_e_grava_o_evento(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None

    resposta = client.post(
        f"/api/v1/tasks/{tarefa.id}/progress", json={"action": "feita"}, headers=login(aluno)
    )

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "feita"
    eventos = list(session.scalars(select(ProgressEvent).where(ProgressEvent.task_id == tarefa.id)))
    assert [e.action for e in eventos] == ["feita"]


def test_tarefa_de_outro_aluno_responde_404(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None
    intruso = Student(phase="formado", mode="independente", email="intruso@exemplo.com")
    session.add(intruso)
    session.commit()

    resposta = client.post(
        f"/api/v1/tasks/{tarefa.id}/progress",
        json={"action": "feita"},
        headers=login(intruso),
    )

    assert resposta.status_code == 404
    session.refresh(tarefa)
    assert tarefa.status == "pendente"


def test_lancar_acertos_soma_na_proficiencia(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    tarefa = session.scalars(select(Task).where(Task.kind == "questoes")).first()
    assert tarefa is not None

    client.post(
        f"/api/v1/tasks/{tarefa.id}/progress",
        json={"action": "feita", "answered": 20, "correct": 14},
        headers=login(aluno),
    )

    proficiencia = session.scalar(
        select(Proficiency).where(
            Proficiency.student_id == tarefa.student_id,
            Proficiency.topic_id == tarefa.topic_id,
        )
    )
    assert proficiencia is not None
    assert (proficiencia.answered, proficiencia.correct) == (20, 14)


def test_acertos_acima_das_questoes_sao_recusados(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None

    resposta = client.post(
        f"/api/v1/tasks/{tarefa.id}/progress",
        json={"action": "feita", "answered": 5, "correct": 9},
        headers=login(aluno),
    )
    assert resposta.status_code == 422


def test_tarefa_inexistente_da_404(client: TestClient, aluno: Student, login) -> None:  # type: ignore[no-untyped-def]
    resposta = client.post(
        f"/api/v1/tasks/{uuid.uuid4()}/progress",
        json={"action": "feita"},
        headers=login(aluno),
    )
    assert resposta.status_code == 404


def test_seed_rodado_duas_vezes_nao_duplica_o_dia(session: Session, aluno: Student) -> None:
    primeiro = len(list(session.scalars(select(Task))))

    seed(session, today=HOJE)
    session.commit()

    assert len(list(session.scalars(select(Task)))) == primeiro
