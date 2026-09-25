from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, TargetExam
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session)
    session.commit()
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    return student


def test_projecao_diz_que_o_plano_cabe(client: TestClient, aluno: Student, login) -> None:  # type: ignore[no-untyped-def]
    corpo = client.get("/api/v1/me/plan/projection", headers=login(aluno)).json()

    assert corpo["fits"] is True
    assert corpo["missing_minutes"] == 0
    assert corpo["extra_minutes_per_day"] == 0
    assert corpo["unscheduled_topics"] == []
    assert corpo["days_left"] > 0


def test_projecao_de_plano_que_nao_cabe_traz_as_opcoes(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == aluno.id))
    assert alvo is not None
    alvo.exam_date = date.today() + timedelta(days=1)
    session.commit()

    corpo = client.get("/api/v1/me/plan/projection", headers=login(aluno)).json()

    assert corpo["fits"] is False
    assert corpo["missing_minutes"] > 0
    assert corpo["extra_minutes_per_day"] > 0
    assert corpo["unscheduled_topics"]
    # Vêm nomes de tema, não uuids.
    assert all(t.count("-") < 4 for t in corpo["unscheduled_topics"])


def test_replanejar_pela_api_gera_versao_nova(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    corpo = client.post("/api/v1/me/plan/replan", headers=login(aluno)).json()

    assert corpo["plan_version"] >= 2
    assert corpo["created"] > 0
    assert corpo["summary"]


def test_projecao_de_aluno_sem_prova_principal_da_409(
    client: TestClient,
    session: Session,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == aluno.id))
    assert alvo is not None
    alvo.is_primary = False
    session.commit()

    assert client.get("/api/v1/me/plan/projection", headers=login(aluno)).status_code == 409


def test_projecao_sem_sessao_e_recusada(client: TestClient, aluno: Student) -> None:
    assert client.get("/api/v1/me/plan/projection").status_code == 401
