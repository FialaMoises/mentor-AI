"""Carrega o catálogo no banco. Idempotente: rodar de novo atualiza, não duplica."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TOPIC_LEVEL_AREA, TOPIC_LEVEL_SUBTEMA, TOPIC_LEVEL_TEMA
from ..models import Exam as ExamRow
from ..models import Topic as TopicRow
from ..models import TopicIncidence as IncidenceRow
from .schema import Catalog

CATALOG_PATH = Path(__file__).resolve().parents[3].parent / "db" / "catalog" / "base-canonica.yaml"


@dataclass(frozen=True, slots=True)
class LoadReport:
    areas: int
    temas: int
    subtemas: int
    incidences: int

    def __str__(self) -> str:
        return (
            f"{self.areas} áreas, {self.temas} temas, {self.subtemas} subtemas, "
            f"{self.incidences} pesos de incidência"
        )


def read_catalog(path: Path | None = None) -> Catalog:
    raw = yaml.safe_load((path or CATALOG_PATH).read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)


def _upsert_topic(
    session: Session,
    *,
    slug: str,
    name: str,
    area: str,
    level: int,
    position: int,
    parent_id: object | None,
) -> TopicRow:
    topic = session.scalar(select(TopicRow).where(TopicRow.slug == slug))
    if topic is None:
        topic = TopicRow(slug=slug)
        session.add(topic)
    topic.name = name
    topic.area = area
    topic.level = level
    topic.position = position
    topic.parent_id = parent_id  # type: ignore[assignment]
    return topic


def load(session: Session, path: Path | None = None) -> LoadReport:
    catalog = read_catalog(path)

    exam = session.scalar(select(ExamRow).where(ExamRow.slug == catalog.exam.slug))
    if exam is None:
        exam = ExamRow(slug=catalog.exam.slug)
        session.add(exam)
    exam.name = catalog.exam.name
    exam.authority = catalog.exam.authority
    exam.notes = catalog.exam.notes
    session.flush()

    temas = subtemas = 0
    leaf_rows: dict[str, TopicRow] = {}

    for area_pos, area in enumerate(catalog.areas):
        area_row = _upsert_topic(
            session,
            slug=area.slug,
            name=area.name,
            area=area.name,
            level=TOPIC_LEVEL_AREA,
            position=area_pos,
            parent_id=None,
        )
        session.flush()

        for tema_pos, tema in enumerate(area.temas):
            tema_row = _upsert_topic(
                session,
                slug=tema.slug,
                name=tema.name,
                area=area.name,
                level=TOPIC_LEVEL_TEMA,
                position=tema_pos,
                parent_id=area_row.id,
            )
            session.flush()
            temas += 1

            for sub_pos, sub in enumerate(tema.subtemas):
                sub_row = _upsert_topic(
                    session,
                    slug=sub.slug,
                    name=sub.name,
                    area=area.name,
                    level=TOPIC_LEVEL_SUBTEMA,
                    position=sub_pos,
                    parent_id=tema_row.id,
                )
                leaf_rows[sub.slug] = sub_row
                subtemas += 1
    session.flush()

    # O peso bruto vira incidência normalizada: o maior subtema vale 1.0.
    leaves = catalog.leaves()
    maior = max(peso for *_, peso in leaves)
    for _area, _tema, sub, peso in leaves:
        topic = leaf_rows[sub.slug]
        incidence = session.scalar(
            select(IncidenceRow).where(
                IncidenceRow.topic_id == topic.id, IncidenceRow.exam_id == exam.id
            )
        )
        if incidence is None:
            incidence = IncidenceRow(topic_id=topic.id, exam_id=exam.id)
            session.add(incidence)
        incidence.weight = peso / maior
        incidence.source = catalog.weights.default_source
        incidence.checked_at = catalog.weights.checked_at
    session.flush()

    return LoadReport(
        areas=len(catalog.areas), temas=temas, subtemas=subtemas, incidences=len(leaves)
    )
