from __future__ import annotations

from pathlib import Path

import pytest

from app.storage import FileSystemStore, StorageError


def test_guarda_e_devolve_o_arquivo(tmp_path: Path) -> None:
    store = FileSystemStore(tmp_path)

    store.put("routines/aluno/arquivo.pdf", b"%PDF-1.7", "application/pdf")

    assert store.get("routines/aluno/arquivo.pdf") == b"%PDF-1.7"
    assert (tmp_path / "routines" / "aluno" / "arquivo.pdf").exists()


def test_sobrescrever_a_mesma_chave_troca_o_conteudo(tmp_path: Path) -> None:
    store = FileSystemStore(tmp_path)
    store.put("a/b.pdf", b"velho", "application/pdf")

    store.put("a/b.pdf", b"novo", "application/pdf")

    assert store.get("a/b.pdf") == b"novo"


def test_apagar_e_idempotente(tmp_path: Path) -> None:
    store = FileSystemStore(tmp_path)
    store.put("a/b.pdf", b"x", "application/pdf")

    store.delete("a/b.pdf")
    store.delete("a/b.pdf")

    with pytest.raises(StorageError):
        store.get("a/b.pdf")


def test_chave_que_tenta_sair_da_raiz_nao_passa(tmp_path: Path) -> None:
    store = FileSystemStore(tmp_path / "raiz")
    vizinho = tmp_path / "segredo.txt"
    vizinho.write_text("não é para ler")

    # Os saltos são descartados: a chave vira um caminho dentro da raiz.
    store.put("../segredo.txt", b"tentativa", "text/plain")

    assert vizinho.read_text() == "não é para ler"
    assert (tmp_path / "raiz" / "segredo.txt").read_bytes() == b"tentativa"


def test_chave_vazia_e_recusada(tmp_path: Path) -> None:
    store = FileSystemStore(tmp_path)

    with pytest.raises(StorageError):
        store.put("///", b"x", "text/plain")


def test_a_raiz_e_criada_se_nao_existir(tmp_path: Path) -> None:
    destino = tmp_path / "nao" / "existe" / "ainda"

    FileSystemStore(destino)

    assert destino.is_dir()
