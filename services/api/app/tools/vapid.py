"""Gera o par de chaves VAPID do Web Push.

Roda com `python -m app.tools.vapid` e devolve as duas linhas para o `.env`.
A chave privada é segredo: nunca versionada, nunca em log.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def generate() -> tuple[str, str]:
    """Devolve (chave pública, chave privada) no formato que o Web Push espera."""
    privada = ec.generate_private_key(ec.SECP256R1())
    publica = privada.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    numero = privada.private_numbers().private_value
    return _b64(publica), _b64(numero.to_bytes(32, "big"))


def main() -> None:
    publica, privada = generate()
    print(f"VAPID_PUBLIC_KEY={publica}")
    print(f"VAPID_PRIVATE_KEY={privada}")


if __name__ == "__main__":
    main()
