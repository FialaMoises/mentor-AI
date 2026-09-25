from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.deps import get_extraction_provider, get_object_store
from app.extraction import FakeExtractor
from app.main import app
from app.models import Base
from app.storage import InMemoryStore


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("pragma foreign_keys=on")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def api_store() -> InMemoryStore:
    """O object store que a API usa nos testes — nada sai da memória."""
    return InMemoryStore()


@pytest.fixture
def api_provider() -> FakeExtractor:
    """O dublê da extração. O teste ajusta `payload` antes de subir o arquivo."""
    return FakeExtractor()


@pytest.fixture
def client(
    session: Session, api_store: InMemoryStore, api_provider: FakeExtractor
) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        yield session
        session.commit()

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_object_store] = lambda: api_store
    app.dependency_overrides[get_extraction_provider] = lambda: api_provider
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
