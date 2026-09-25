from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.catalog import load


def test_catalogo_volta_como_arvore_de_tres_niveis(client: TestClient, session: Session) -> None:
    load(session)
    session.commit()

    resposta = client.get("/api/v1/catalog/enamed")
    corpo = resposta.json()

    assert resposta.status_code == 200
    assert corpo["exam"] == "enamed"
    assert len(corpo["areas"]) == 7

    area = next(a for a in corpo["areas"] if a["slug"] == "clinica-medica")
    tema = next(t for t in area["temas"] if t["slug"] == "cardiologia")
    slugs = [s["slug"] for s in tema["subtemas"]]
    assert "insuficiencia-cardiaca" in slugs


def test_todo_subtema_da_resposta_tem_peso_e_a_fonte_vem_junto(
    client: TestClient, session: Session
) -> None:
    load(session)
    session.commit()

    corpo = client.get("/api/v1/catalog/enamed").json()

    assert "peso uniforme" in corpo["weights_source"]
    subtemas = [s for a in corpo["areas"] for t in a["temas"] for s in t["subtemas"]]
    assert subtemas
    assert all(0 < s["incidence"] <= 1 for s in subtemas)


def test_prova_desconhecida_da_404(client: TestClient, session: Session) -> None:
    load(session)
    session.commit()

    assert client.get("/api/v1/catalog/prova-que-nao-existe").status_code == 404
