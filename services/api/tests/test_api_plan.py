from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Proficiency, ProgressEvent, Task
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_lista_do_dia_traz_as_tarefas_do_seed(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()

    resposta = client.get(f"/api/v1/students/{SEED_STUDENT_ID}/plan/today")
    corpo = resposta.json()

    assert resposta.status_code == 200
    assert corpo["capacity_minutes"] == 180
    assert corpo["light"] is False
    assert corpo["plan_version"] == 1
    assert len(corpo["tasks"]) > 0
    assert sum(t["minutes"] for t in corpo["tasks"]) <= corpo["capacity_minutes"]
    assert {t["status"] for t in corpo["tasks"]} == {"pendente"}


def test_aluno_inexistente_da_404(client: TestClient) -> None:
    resposta = client.get(f"/api/v1/students/{uuid.uuid4()}/plan/today")
    assert resposta.status_code == 404


def test_marcar_feito_muda_o_status_e_grava_o_evento(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None

    resposta = client.post(f"/api/v1/tasks/{tarefa.id}/progress", json={"action": "feita"})

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "feita"
    eventos = list(session.scalars(select(ProgressEvent).where(ProgressEvent.task_id == tarefa.id)))
    assert [e.action for e in eventos] == ["feita"]


def test_lancar_acertos_soma_na_proficiencia(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()
    tarefa = session.scalars(select(Task).where(Task.kind == "questoes")).first()
    assert tarefa is not None

    client.post(
        f"/api/v1/tasks/{tarefa.id}/progress",
        json={"action": "feita", "answered": 20, "correct": 14},
    )

    proficiencia = session.scalar(
        select(Proficiency).where(
            Proficiency.student_id == tarefa.student_id,
            Proficiency.topic_id == tarefa.topic_id,
        )
    )
    assert proficiencia is not None
    assert (proficiencia.answered, proficiencia.correct) == (20, 14)


def test_acertos_acima_das_questoes_sao_recusados(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None

    resposta = client.post(
        f"/api/v1/tasks/{tarefa.id}/progress",
        json={"action": "feita", "answered": 5, "correct": 9},
    )
    assert resposta.status_code == 422


def test_acao_invalida_e_recusada(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()
    tarefa = session.scalars(select(Task)).first()
    assert tarefa is not None

    resposta = client.post(f"/api/v1/tasks/{tarefa.id}/progress", json={"action": "quase"})
    assert resposta.status_code == 422


def test_tarefa_inexistente_da_404(client: TestClient) -> None:
    resposta = client.post(f"/api/v1/tasks/{uuid.uuid4()}/progress", json={"action": "feita"})
    assert resposta.status_code == 404


def test_seed_rodado_duas_vezes_nao_duplica_o_dia(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()
    primeiro = len(list(session.scalars(select(Task))))

    seed(session)
    session.commit()
    assert len(list(session.scalars(select(Task)))) == primeiro
