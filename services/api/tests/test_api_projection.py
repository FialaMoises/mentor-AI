from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TargetExam
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

ROTA = f"/api/v1/students/{SEED_STUDENT_ID}/plan"


def test_projecao_diz_que_o_plano_cabe(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()

    corpo = client.get(f"{ROTA}/projection").json()

    assert corpo["fits"] is True
    assert corpo["missing_minutes"] == 0
    assert corpo["extra_minutes_per_day"] == 0
    assert corpo["unscheduled_topics"] == []
    assert corpo["days_left"] > 0


def test_projecao_de_plano_que_nao_cabe_traz_as_opcoes(
    client: TestClient, session: Session
) -> None:
    seed(session)
    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == SEED_STUDENT_ID))
    assert alvo is not None
    alvo.exam_date = date.today() + timedelta(days=1)
    session.commit()

    corpo = client.get(f"{ROTA}/projection").json()

    assert corpo["fits"] is False
    assert corpo["missing_minutes"] > 0
    assert corpo["extra_minutes_per_day"] > 0
    # Vêm nomes de tema, não uuids.
    assert corpo["unscheduled_topics"]
    assert all(not t.count("-") >= 4 for t in corpo["unscheduled_topics"])


def test_replanejar_pela_api_gera_versao_nova(client: TestClient, session: Session) -> None:
    seed(session)
    session.commit()

    corpo = client.post(f"{ROTA}/replan").json()

    assert corpo["plan_version"] >= 2
    assert corpo["created"] > 0
    assert corpo["summary"]


def test_projecao_de_aluno_sem_prova_principal_da_409(client: TestClient, session: Session) -> None:
    seed(session)
    alvo = session.scalar(select(TargetExam).where(TargetExam.student_id == SEED_STUDENT_ID))
    assert alvo is not None
    alvo.is_primary = False
    session.commit()

    assert client.get(f"{ROTA}/projection").status_code == 409
