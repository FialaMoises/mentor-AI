"""Dependências que o teste troca: o object store e o provedor de extração."""

from __future__ import annotations

from .extraction.provider import ExtractionProvider, get_provider
from .storage import ObjectStore


def get_object_store() -> ObjectStore:
    from .storage.s3 import get_store

    return get_store()


def get_extraction_provider() -> ExtractionProvider:
    return get_provider()
