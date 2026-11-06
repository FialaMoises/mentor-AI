from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import request_login
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


def entrar(client: TestClient, session: Session, email: str = "novo@exemplo.com") -> dict[str, str]:
    """Faz o caminho real: pede o link, troca pelo token, devolve o cabeçalho."""
    load_catalog(session)
    session.commit()
    assert client.post("/api/v1/auth/magic-link", json={"email": email}).status_code == 202
    link = request_login(session, email)
    session.commit()
    corpo = client.post("/api/v1/auth/verify", json={"token": link.token}).json()
    return {"Authorization": f"Bearer {corpo['token']}"}


def test_aluno_novo_entra_precisando_de_onboarding(client: TestClient, session: Session) -> None:
    load_catalog(session)
    session.commit()
    link = request_login(session, "novo@exemplo.com")
    session.commit()

    corpo = client.post("/api/v1/auth/verify", json={"token": link.token}).json()

    assert corpo["needs_onboarding"] is True
    assert corpo["token"]


def test_questionario_preenche_o_aluno_com_autoavaliacao_por_area(
    client: TestClient, session: Session
) -> None:
    cabecalho = entrar(client, session)

    corpo = client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho).json()

    assert corpo["weekly_hours"] == 14
    # Clínica médica e pediatria têm dezenas de subtemas; todos herdam a nota da área.
    assert corpo["topics_assessed"] > 20
    assert corpo["consent_required"] is True


def test_refazer_o_questionario_substitui_as_respostas(
    client: TestClient, session: Session
) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)

    outro = {**QUESTIONARIO, "self_assessment": {"pediatria": 0.9}}
    corpo = client.put("/api/v1/me/profile", json=outro, headers=cabecalho).json()

    provas = list(session.scalars(select(TargetExam)))
    assert len(provas) == 1
    assert corpo["topics_assessed"] < 40


def test_questionario_sem_sessao_e_recusado(client: TestClient, session: Session) -> None:
    load_catalog(session)
    session.commit()

    assert client.put("/api/v1/me/profile", json=QUESTIONARIO).status_code == 401


def test_questionario_sem_prova_principal_e_recusado(client: TestClient, session: Session) -> None:
    cabecalho = entrar(client, session)
    payload = {**QUESTIONARIO, "exams": [{"name": "ENAMED", "exam_date": PROVA}]}

    assert client.put("/api/v1/me/profile", json=payload, headers=cabecalho).status_code == 422


def test_questionario_com_area_desconhecida_e_recusado(
    client: TestClient, session: Session
) -> None:
    cabecalho = entrar(client, session)
    payload = {**QUESTIONARIO, "self_assessment": {"area-que-nao-existe": 0.5}}

    assert client.put("/api/v1/me/profile", json=payload, headers=cabecalho).status_code == 422


def test_consentimento_e_registrado_uma_vez(client: TestClient, session: Session) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)

    primeiro = client.post("/api/v1/me/consent", headers=cabecalho).json()
    client.post("/api/v1/me/consent", headers=cabecalho)

    assert primeiro["accepted"] is True
    assert len(list(session.scalars(select(Consent)))) == 1


def test_upload_antes_do_consentimento_e_bloqueado(client: TestClient, session: Session) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)

    resposta = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=cabecalho,
    )

    assert resposta.status_code == 403


def test_upload_extrai_e_devolve_a_semana_para_conferir(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)
    client.post("/api/v1/me/consent", headers=cabecalho)
    api_provider.payload = ROTINA

    corpo = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=cabecalho,
    ).json()

    assert corpo["status"] == "extraido"
    assert corpo["extracted"]["commitments"][0]["label"] == "Internato"
    assert corpo["original_kept"] is True
    assert corpo["edited_blocks"] == 0


def test_documento_de_outro_aluno_responde_404(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    dono = entrar(client, session, "dono@exemplo.com")
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=dono)
    client.post("/api/v1/me/consent", headers=dono)
    api_provider.payload = ROTINA
    documento = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=dono,
    ).json()

    intruso = entrar(client, session, "intruso@exemplo.com")
    resposta = client.get(f"/api/v1/documents/{documento['id']}", headers=intruso)

    assert resposta.status_code == 404


def test_confirmar_a_semana_replaneja_e_devolve_o_resumo(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)
    client.post("/api/v1/me/consent", headers=cabecalho)
    api_provider.payload = ROTINA
    documento = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=cabecalho,
    ).json()

    corpo = client.post(
        f"/api/v1/documents/{documento['id']}/confirm", json=ROTINA, headers=cabecalho
    ).json()

    assert corpo["commitments"] == 1
    assert corpo["days_recalculated"] > 0
    assert corpo["replan_summary"]
    assert corpo["document"]["status"] == "confirmado"


def test_aluno_pode_apagar_o_documento(
    client: TestClient, session: Session, api_store: InMemoryStore
) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)
    client.post("/api/v1/me/consent", headers=cabecalho)
    documento = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=cabecalho,
    ).json()

    assert (
        client.delete(f"/api/v1/documents/{documento['id']}", headers=cabecalho).status_code == 204
    )
    assert len(api_store) == 0
    assert not list(session.scalars(select(Document)))


def test_aluno_escolhe_qual_prova_e_a_principal(client: TestClient, session: Session) -> None:
    cabecalho = entrar(client, session)
    payload = {
        **QUESTIONARIO,
        "exams": [
            {"name": "ENAMED", "exam_date": PROVA, "is_primary": True},
            {"name": "USP", "exam_date": PROVA, "is_primary": False},
        ],
    }
    client.put("/api/v1/me/profile", json=payload, headers=cabecalho)
    usp = next(p for p in session.scalars(select(TargetExam).where(TargetExam.name == "USP")))

    resposta = client.post(f"/api/v1/me/exams/{usp.id}/primary", headers=cabecalho)

    assert resposta.status_code == 200
    principais = [p for p in session.scalars(select(TargetExam)) if p.is_primary]
    assert [p.name for p in principais] == ["USP"]


def test_aluno_novo_tem_plano_depois_de_confirmar_a_rotina(
    client: TestClient, session: Session, api_provider: FakeExtractor
) -> None:
    cabecalho = entrar(client, session)
    client.put("/api/v1/me/profile", json=QUESTIONARIO, headers=cabecalho)
    client.post("/api/v1/me/consent", headers=cabecalho)
    api_provider.payload = ROTINA
    documento = client.post(
        "/api/v1/me/documents",
        files={"file": ("grade.pdf", PDF, "application/pdf")},
        data={"kind": "grade"},
        headers=cabecalho,
    ).json()
    client.post(f"/api/v1/documents/{documento['id']}/confirm", json=ROTINA, headers=cabecalho)

    projecao = client.get("/api/v1/me/plan/projection", headers=cabecalho).json()
    assert projecao["days_left"] > 0


def test_um_aluno_por_email(client: TestClient, session: Session) -> None:
    entrar(client, session, "mesmo@exemplo.com")
    entrar(client, session, "mesmo@exemplo.com")

    alunos = list(session.scalars(select(Student).where(Student.email == "mesmo@exemplo.com")))
    assert len(alunos) == 1
