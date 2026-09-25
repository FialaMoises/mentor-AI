from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog import CATALOG_PATH, Catalog, load, read_catalog
from app.models import (
    TOPIC_LEVEL_AREA,
    TOPIC_LEVEL_SUBTEMA,
    TOPIC_LEVEL_TEMA,
    Exam,
    Topic,
    TopicIncidence,
)


def test_o_catalogo_do_repo_e_valido() -> None:
    catalogo = read_catalog()
    assert CATALOG_PATH.exists()
    assert catalogo.exam.slug == "enamed"
    assert len(catalogo.areas) == 7


def test_toda_area_tem_tema_e_todo_tema_tem_subtema() -> None:
    for area in read_catalog().areas:
        assert area.temas, f"{area.slug} sem temas"
        for tema in area.temas:
            assert tema.subtemas, f"{tema.slug} sem subtemas"


def test_carga_cria_a_arvore_de_tres_niveis(session: Session) -> None:
    catalogo = read_catalog()
    report = load(session)
    session.flush()

    assert report.areas == len(catalogo.areas)
    assert report.subtemas == len(catalogo.leaves())

    níveis = {
        nível: session.scalar(select(func.count()).select_from(Topic).where(Topic.level == nível))
        for nível in (TOPIC_LEVEL_AREA, TOPIC_LEVEL_TEMA, TOPIC_LEVEL_SUBTEMA)
    }
    assert níveis[TOPIC_LEVEL_AREA] == report.areas
    assert níveis[TOPIC_LEVEL_TEMA] == report.temas
    assert níveis[TOPIC_LEVEL_SUBTEMA] == report.subtemas


def test_todo_subtema_tem_pai_e_toda_area_e_raiz(session: Session) -> None:
    load(session)
    session.flush()

    for topic in session.scalars(select(Topic)):
        if topic.level == TOPIC_LEVEL_AREA:
            assert topic.parent_id is None, f"{topic.slug} é área e tem pai"
        else:
            assert topic.parent_id is not None, f"{topic.slug} está solto na árvore"


def test_todo_subtema_tem_peso_com_origem_registrada(session: Session) -> None:
    load(session)
    session.flush()

    subtemas = list(session.scalars(select(Topic).where(Topic.level == TOPIC_LEVEL_SUBTEMA)))
    incidências = list(session.scalars(select(TopicIncidence)))

    assert len(incidências) == len(subtemas)
    for incidência in incidências:
        assert 0 < incidência.weight <= 1
        assert incidência.source.strip(), "peso sem fonte não entra na base"
        assert incidência.checked_at is not None


def test_carga_repetida_nao_duplica_nada(session: Session) -> None:
    load(session)
    session.flush()
    antes = (
        session.scalar(select(func.count()).select_from(Topic)),
        session.scalar(select(func.count()).select_from(TopicIncidence)),
        session.scalar(select(func.count()).select_from(Exam)),
    )

    load(session)
    session.flush()
    depois = (
        session.scalar(select(func.count()).select_from(Topic)),
        session.scalar(select(func.count()).select_from(TopicIncidence)),
        session.scalar(select(func.count()).select_from(Exam)),
    )

    assert antes == depois


def test_carga_corrige_nome_editado_no_banco_sem_trocar_o_id(session: Session) -> None:
    load(session)
    session.flush()
    tema = session.scalar(select(Topic).where(Topic.slug == "insuficiencia-cardiaca"))
    assert tema is not None
    id_original, nome_original = tema.id, tema.name

    tema.name = "Nome errado"
    session.flush()
    load(session)
    session.flush()

    session.refresh(tema)
    assert (tema.id, tema.name) == (id_original, nome_original)


def test_arquivo_com_slug_fora_do_padrao_e_recusado() -> None:
    bruto = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    bruto["areas"][0]["slug"] = "Clínica Médica"

    with pytest.raises(ValidationError):
        Catalog.model_validate(bruto)


def test_arquivo_com_slug_repetido_e_recusado() -> None:
    bruto = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    bruto["areas"][1]["slug"] = bruto["areas"][0]["slug"]

    with pytest.raises(ValidationError, match="slug repetido"):
        Catalog.model_validate(bruto)


def test_tema_sem_subtema_e_recusado() -> None:
    bruto = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    bruto["areas"][0]["temas"][0]["subtemas"] = []

    with pytest.raises(ValidationError):
        Catalog.model_validate(bruto)


def test_peso_fora_da_faixa_e_recusado() -> None:
    bruto = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    bruto["areas"][0]["weight"] = 1.5

    with pytest.raises(ValidationError):
        Catalog.model_validate(bruto)


def test_fonte_do_peso_nao_pode_ser_vazia() -> None:
    bruto = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    bruto["weights"]["default_source"] = ""

    with pytest.raises(ValidationError):
        Catalog.model_validate(bruto)
