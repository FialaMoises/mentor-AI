"""Validação do catálogo versionado em `db/catalog/`.

O arquivo YAML é dado de entrada como qualquer outro: nada dele entra no banco
sem passar por aqui.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str = Field(min_length=2, max_length=160)
    weight: float = Field(default=1.0, gt=0.0, le=1.0)

    @field_validator("slug")
    @classmethod
    def slug_em_kebab(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError(f"slug fora do padrão kebab-case: {value!r}")
        return value


class Subtema(Node):
    pass


class Tema(Node):
    subtemas: list[Subtema] = Field(min_length=1)


class Area(Node):
    temas: list[Tema] = Field(min_length=1)


class ExamSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str = Field(min_length=2, max_length=160)
    authority: str = ""
    notes: str = ""

    @field_validator("slug")
    @classmethod
    def slug_em_kebab(cls, value: str) -> str:
        if not SLUG.match(value):
            raise ValueError(f"slug fora do padrão kebab-case: {value!r}")
        return value


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_source: str = Field(min_length=10, max_length=400)
    checked_at: date | None = None


class Catalog(BaseModel):
    """O catálogo inteiro, já validado."""

    model_config = ConfigDict(extra="forbid")

    version: int
    exam: ExamSpec
    weights: Weights
    areas: list[Area] = Field(min_length=1)

    @model_validator(mode="after")
    def slugs_unicos(self) -> Catalog:
        vistos: set[str] = set()
        for area in self.areas:
            for node in (area, *area.temas, *(s for t in area.temas for s in t.subtemas)):
                if node.slug in vistos:
                    raise ValueError(f"slug repetido no catálogo: {node.slug!r}")
                vistos.add(node.slug)
        return self

    def leaves(self) -> list[tuple[Area, Tema, Subtema, float]]:
        """Subtemas com o peso bruto: área × tema × subtema."""
        return [
            (area, tema, sub, area.weight * tema.weight * sub.weight)
            for area in self.areas
            for tema in area.temas
            for sub in tema.subtemas
        ]
