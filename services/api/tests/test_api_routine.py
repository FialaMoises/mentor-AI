from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.api.routine as rotas
from app.models import Commitment, Student
from app.seed import SEED_STUDENT_ID
from app.seed import run as seed

HOJE = date(2026, 9, 25)  # sexta

ACADEMIA = {
    "kind": "academia",
    "label": "Musculação",
    "weekdays": [0, 2, 4],
    "starts_at": "07:00",
    "duration_minutes": 60,
}


@pytest.fixture(autouse=True)
def dia_fixo(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Congela o relógio da borda e anota com que fuso ele foi consultado."""
    fusos: list[str] = []

    def hoje(fuso: str) -> date:
        fusos.append(fuso)
        return HOJE

    monkeypatch.setattr(rotas, "today_in", hoje)
    return fusos


@pytest.fixture
def aluno(session: Session) -> Student:
    seed(session, today=HOJE)
    student = session.get(Student, SEED_STUDENT_ID)
    assert student is not None
    session.commit()
    return student


@pytest.fixture
def outro(session: Session) -> Student:
    student = Student(phase="formado", mode="independente", timezone="America/Sao_Paulo")
    session.add(student)
    session.commit()
    return student


def test_sem_login_responde_401(client: TestClient) -> None:
    assert client.get("/api/v1/me/routine").status_code == 401
    assert client.post("/api/v1/me/commitment-series", json=ACADEMIA).status_code == 401


def test_cria_lista_edita_e_apaga_uma_serie(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(aluno)

    criada = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=cabecalho)
    assert criada.status_code == 201
    serie = criada.json()["series_id"]
    assert criada.json()["replan_summary"]

    semana = client.get("/api/v1/me/routine?week=2026-09-28", headers=cabecalho).json()
    segunda = semana["days"][0]
    assert segunda["items"][0]["starts_at"] == "07:00"
    assert segunda["items"][0]["series_id"] == serie
    assert semana["days"][1]["items"] == []

    editada = client.patch(
        f"/api/v1/me/commitment-series/{serie}",
        json={**ACADEMIA, "weekdays": [1], "starts_at": "19:30"},
        headers=cabecalho,
    )
    assert editada.status_code == 200
    semana = client.get("/api/v1/me/routine?week=2026-09-28", headers=cabecalho).json()
    assert semana["days"][0]["items"] == []
    assert semana["days"][1]["items"][0]["starts_at"] == "19:30"

    apagada = client.delete(f"/api/v1/me/commitment-series/{serie}", headers=cabecalho)
    assert apagada.status_code == 200
    assert apagada.json()["series_id"] is None
    semana = client.get("/api/v1/me/routine?week=2026-09-28", headers=cabecalho).json()
    assert all(dia["items"] == [] for dia in semana["days"])


def test_serie_de_outro_aluno_responde_404(
    client: TestClient,
    aluno: Student,
    outro: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    serie = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=login(aluno)).json()[
        "series_id"
    ]
    intruso = login(outro)

    assert (
        client.patch(
            f"/api/v1/me/commitment-series/{serie}", json=ACADEMIA, headers=intruso
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/me/commitment-series/{serie}", headers=intruso).status_code == 404
    )


def test_campo_desconhecido_e_recusado(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    resposta = client.post(
        "/api/v1/me/commitment-series",
        json={**ACADEMIA, "student_id": "outro"},
        headers=login(aluno),
    )

    assert resposta.status_code == 422


def test_semanal_e_data_unica_juntos_sao_recusados(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    resposta = client.post(
        "/api/v1/me/commitment-series",
        json={**ACADEMIA, "on_day": "2026-10-08"},
        headers=login(aluno),
    )

    assert resposta.status_code == 422


def test_duracao_e_tipo_fora_da_faixa_sao_recusados(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(aluno)

    longo = {**ACADEMIA, "duration_minutes": 1441}
    estranho = {**ACADEMIA, "kind": "festa"}
    assert (
        client.post("/api/v1/me/commitment-series", json=longo, headers=cabecalho).status_code
        == 422
    )
    assert (
        client.post("/api/v1/me/commitment-series", json=estranho, headers=cabecalho).status_code
        == 422
    )


def test_amanha_e_o_do_fuso_do_aluno(
    client: TestClient,
    session: Session,
    aluno: Student,
    dia_fixo: list[str],
    login,  # type: ignore[no-untyped-def]
) -> None:
    client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=login(aluno))

    assert dia_fixo == ["America/Fortaleza"]
    registros = session.scalars(select(Commitment).where(Commitment.student_id == aluno.id))
    assert {c.starts_on for c in registros} == {date(2026, 9, 26)}


def test_aluno_sem_prova_principal_salva_e_ve_a_semana(
    client: TestClient,
    outro: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(outro)

    criada = client.post("/api/v1/me/commitment-series", json=ACADEMIA, headers=cabecalho)
    semana = client.get("/api/v1/me/routine", headers=cabecalho).json()

    assert criada.status_code == 201
    assert criada.json()["replan_summary"] == ""
    assert len(semana["days"]) == 7
    assert all(dia["computed"] for dia in semana["days"])


def test_semana_normaliza_para_segunda(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    semana = client.get("/api/v1/me/routine?week=2026-10-01", headers=login(aluno)).json()

    assert semana["week_start"] == "2026-09-28"
    assert semana["today"] == "2026-09-25"
    assert [dia["day"] for dia in semana["days"]][-1] == "2026-10-04"


def test_item_da_semana_traz_o_fim_da_vigencia(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    """Sem isso, editar um bloco da grade apagaria a data em que o rodízio acaba."""
    cabecalho = login(aluno)
    client.post(
        "/api/v1/me/commitment-series",
        json={**ACADEMIA, "ends_on": "2026-12-18"},
        headers=cabecalho,
    )

    semana = client.get("/api/v1/me/routine?week=2026-09-28", headers=cabecalho).json()

    assert semana["days"][0]["items"][0]["ends_on"] == "2026-12-18"


def test_item_traz_a_serie_vigente_no_formato_do_formulario(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    cabecalho = login(aluno)
    client.post(
        "/api/v1/me/commitment-series",
        json={**ACADEMIA, "starts_on": "2026-09-30"},
        headers=cabecalho,
    )

    semana = client.get("/api/v1/me/routine?week=2026-09-28", headers=cabecalho).json()

    serie = semana["days"][2]["items"][0]["series"]
    assert serie == {
        "kind": "academia",
        "label": "Musculação",
        "weekdays": [0, 2, 4],
        "on_day": None,
        "starts_at": "07:00",
        "duration_minutes": 60,
        "starts_on": "2026-09-30",
        "ends_on": None,
    }


def test_semana_absurda_responde_422(
    client: TestClient,
    aluno: Student,
    login,  # type: ignore[no-untyped-def]
) -> None:
    resposta = client.get("/api/v1/me/routine?week=9999-12-31", headers=login(aluno))

    assert resposta.status_code == 422
