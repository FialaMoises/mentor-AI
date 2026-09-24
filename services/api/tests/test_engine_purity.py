"""O motor é puro. Este teste falha se alguém encostar banco, rede ou relógio nele."""

from __future__ import annotations

import ast
from pathlib import Path

PROIBIDOS = {
    "sqlalchemy",
    "psycopg",
    "fastapi",
    "requests",
    "httpx",
    "boto3",
    "openai",
    "anthropic",
    "app.db",
    "app.models",
    "app.config",
}

RELOGIO = {("datetime", "now"), ("date", "today"), ("time", "time")}

ENGINE = Path(__file__).resolve().parents[1] / "app" / "engine"


def arquivos() -> list[Path]:
    encontrados = sorted(ENGINE.rglob("*.py"))
    assert encontrados, "não achei o pacote do motor"
    return encontrados


def test_engine_nao_importa_banco_rede_nem_framework() -> None:
    for arquivo in arquivos():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        importados: set[str] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                importados.add(no.module)
        for modulo in importados:
            assert modulo not in PROIBIDOS and modulo.split(".")[0] not in PROIBIDOS, (
                f"{arquivo.name} importa {modulo}: o motor precisa continuar puro"
            )


def test_engine_nao_le_o_relogio() -> None:
    for arquivo in arquivos():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
                chamada = (no.value.id, no.attr)
                assert chamada not in RELOGIO, (
                    f"{arquivo.name} chama {no.value.id}.{no.attr}: a data entra por argumento"
                )
