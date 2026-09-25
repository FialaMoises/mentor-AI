"""`python -m app.catalog` carrega a base canônica no banco."""

from __future__ import annotations

from ..db import SessionLocal
from .loader import load


def main() -> None:
    with SessionLocal() as session:
        report = load(session)
        session.commit()
    print(f"base canônica carregada: {report}")


if __name__ == "__main__":
    main()
