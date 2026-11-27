"""O único lugar da API que olha o relógio.

O motor nunca chama isto: ele recebe a data por argumento. Testes trocam esta
dependência para fixar o dia.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def today_in(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def now_utc() -> datetime:
    """O instante atual, em UTC. Serve aos carimbos (confirmado em, cancelado em)."""
    return datetime.now(UTC)


def monotonic() -> float:
    """Segundos de um relógio que só anda para a frente. Serve ao limite de frequência."""
    return time.monotonic()
