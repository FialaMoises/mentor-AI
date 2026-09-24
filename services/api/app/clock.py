"""O único lugar da API que olha o relógio.

O motor nunca chama isto: ele recebe a data por argumento. Testes trocam esta
dependência para fixar o dia.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def today_in(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()
