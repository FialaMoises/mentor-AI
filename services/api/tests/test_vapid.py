from __future__ import annotations

import base64

from app.tools.vapid import generate


def test_par_de_chaves_tem_o_formato_do_web_push() -> None:
    publica, privada = generate()

    # Chave pública: ponto não comprimido de 65 bytes, começando com 0x04.
    bytes_publica = base64.urlsafe_b64decode(publica + "==")
    assert len(bytes_publica) == 65
    assert bytes_publica[0] == 4
    # Chave privada: o escalar de 32 bytes.
    assert len(base64.urlsafe_b64decode(privada + "==")) == 32


def test_cada_chamada_gera_um_par_novo() -> None:
    assert generate() != generate()


def test_chaves_vem_em_base64url_sem_padding() -> None:
    for chave in generate():
        assert "=" not in chave
        assert "+" not in chave and "/" not in chave
