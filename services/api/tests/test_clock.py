"""Quem lê o relógio é a borda (regra 15): `app/clock.py` e mais ninguém."""

from __future__ import annotations

import ast
from datetime import UTC
from pathlib import Path

from app.clock import now_utc

APP = Path(__file__).resolve().parents[1] / "app"
CLOCK = APP / "clock.py"

RELOGIO = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("date", "today"),
    ("time", "time"),
    ("time", "monotonic"),
}


def test_so_o_clock_le_o_relogio() -> None:
    arquivos = sorted(p for p in APP.rglob("*.py") if p != CLOCK)
    assert arquivos, "não achei o pacote app"
    for arquivo in arquivos:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
                chamada = (no.value.id, no.attr)
                assert chamada not in RELOGIO, (
                    f"{arquivo.relative_to(APP)} chama {no.value.id}.{no.attr}: use app.clock"
                )


def test_agora_vem_com_fuso_utc() -> None:
    assert now_utc().tzinfo is UTC
