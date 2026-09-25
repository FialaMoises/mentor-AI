from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import load as load_catalog
from app.extraction import FakeExtractor
from app.models import Consent, Document, Student, TargetExam
from app.storage import InMemoryStore

PROVA = (date.today() + timedelta(days=150)).isoformat()
PDF = b"%PDF-1.7\n" + b"0" * 200

QUESTIONARIO = {
    "phase": "faculdade",
    "mode": "independente",
    "timezone": "America/Fortaleza",
    "weekly_hours": 14,
    "exams": [{"name": "ENAMED", "exam_date": PROVA, "is_primary": True}],
    "self_assessment": {"clinica-medica": 0.4, "pediatria": 0.2},
}

ROTINA = {
    "commitments": [{"kind": "aula", "label": "Internato", "weekday": 0, "duration_minutes": 240}],
    "exams": [],
    "unreadable": [],
}


def cria_aluno(client: TestClient, session: Session) -> str:
    load_catalog(session)
    session.commit()
    resposta = client.post("/api/v1/students", json=QUESTIONARIO)
    assert resposta.status_code == 201, resposta.text
    return str(resposta.json()["id"])


def test_questionario_cria_aluno_com_autoavaliacao_por_area(
    client: TestClient, session: Session
) -> None:
    load_catalog(session)
    session.commit()

    corpo = client.post("/api/v1/students", json=QUESTIONARIO).json()

    assert corpo["weekly_hours"] == 14
    # Clínica médica e pediatria têm dezenas de subtemas; todos herdam a nota da área.
    assert corpo["topics_assessed"] > 20
    assert corpo["consent_required"] is True


def test_questionario_sem_prova_principal_e_recusado(client: TestClient, session: Session) -> None:
    load_catalog(session)
    session.commit()
    payload = {**QUESTIONARIO, "exams": [{"name": "ENAMED", "exam_date": PROVA}]}

    assert client.post("/api/v1/students", json=payload).status_code == 422


def test_questionario_com_area_desconhecida_e_recusado(
    client: TestClient, session: Session
) -> None:
    load_catalog(session)
    session.commit()
    payload = {**QUESTIONARIO, "self_assessment": {"area-que-nao-existe": 0.5}}

    assert client.post("/api/v1/students", json=payload).status_code == 422


def test_autoavaliacao_fora_da_faixa_e_recusada(client: TestClient, session: Session) -> None:
    load_catalog(session)
    session.commit()
    payload = {**QUESTIONARIO, "self_assessment": {"pediatria": 3}}

    assert client.post("/api/v1/students", json=payload).status_code == 422


def test_consentimento_e_registrado_uma_vez(client: TestClient, session: Session) -> None:
    aluno_id = cria_aluno(client, session)

    primeiro = client.post(f"/api/v1/students/{aluno_id}/consent").json()
    client.post(f"/api/v1/students/{aluno_id}/consent")

    assert primeiro["accepted"] is True
    assert primeiro["policy_version"]
    assert len(list(session.scalars(select(Consent)))) == 1


def test_upload_antes_do_consentimento_e_bloqueado(client: TestClient, session: Session) -> None:
    aluno_id = cria_aluno(client, session)

    resposta = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
    )

    assert resposta.status_code == 403


def test_upload_extrai_e_devolve_a_semana_para_conferir(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    aluno_id = cria_aluno(client, session)
    client.post(f"/api/v1/students/{aluno_id}/consent")
    api_provider.payload = ROTINA

    corpo = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
    ).json()

    assert corpo["status"] == "extraido"
    assert corpo["extracted"]["commitments"][0]["label"] == "Internato"
    assert corpo["original_kept"] is True


def test_upload_de_executavel_disfarcado_e_recusado(client: TestClient, session: Session) -> None:
    aluno_id = cria_aluno(client, session)
    client.post(f"/api/v1/students/{aluno_id}/consent")

    resposta = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", b"MZ\x90\x00 nao sou pdf", "application/pdf")},
        data={"kind": "grade"},
    )

    assert resposta.status_code == 422


def test_confirmar_a_semana_replaneja_e_devolve_o_resumo(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    aluno_id = cria_aluno(client, session)
    client.post(f"/api/v1/students/{aluno_id}/consent")
    api_provider.payload = ROTINA
    documento = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
    ).json()

    corpo = client.post(f"/api/v1/documents/{documento['id']}/confirm", json=ROTINA).json()

    assert corpo["commitments"] == 1
    assert corpo["days_recalculated"] > 0
    assert corpo["replan_summary"]
    assert corpo["document"]["status"] == "confirmado"


def test_aluno_pode_apagar_o_documento(
    client: TestClient, session: Session, api_store: InMemoryStore
) -> None:
    aluno_id = cria_aluno(client, session)
    client.post(f"/api/v1/students/{aluno_id}/consent")
    documento = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
    ).json()

    assert client.delete(f"/api/v1/documents/{documento['id']}").status_code == 204
    assert len(api_store) == 0
    assert not list(session.scalars(select(Document)))


def test_aluno_escolhe_qual_prova_e_a_principal(client: TestClient, session: Session) -> None:
    load_catalog(session)
    session.commit()
    payload = {
        **QUESTIONARIO,
        "exams": [
            {"name": "ENAMED", "exam_date": PROVA, "is_primary": True},
            {"name": "USP", "exam_date": PROVA, "is_primary": False},
        ],
    }
    aluno_id = client.post("/api/v1/students", json=payload).json()["id"]
    usp = next(p for p in session.scalars(select(TargetExam).where(TargetExam.name == "USP")))

    resposta = client.post(f"/api/v1/students/{aluno_id}/exams/{usp.id}/primary")

    assert resposta.status_code == 200
    principais = [p for p in session.scalars(select(TargetExam)) if p.is_primary]
    assert [p.name for p in principais] == ["USP"]


def test_aluno_novo_tem_plano_depois_de_confirmar_a_rotina(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    aluno_id = cria_aluno(client, session)
    client.post(f"/api/v1/students/{aluno_id}/consent")
    api_provider.payload = ROTINA
    documento = client.post(
        f"/api/v1/students/{aluno_id}/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
    ).json()
    client.post(f"/api/v1/documents/{documento['id']}/confirm", json=ROTINA)

    aluno = session.get(Student, uuid.UUID(aluno_id))
    assert aluno is not None
    projecao = client.get(f"/api/v1/students/{aluno_id}/plan/projection").json()
    assert projecao["days_left"] > 0
