"""Limite de frequência da API.

Uma janela deslizante por chave, em memória. A chave é o aluno (pelo hash do
token da sessão) ou, sem login, o IP. Os números vêm da configuração, e o
relógio vem de `app.clock` — este módulo não lê hora nenhuma sozinho.

Em memória quer dizer por processo: com várias réplicas da API, cada uma conta
o seu. Para o piloto, com uma instância só, basta; com mais de uma, o mesmo
`RateLimiter` passa a precisar de um armazenamento compartilhado (Redis).
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections import deque

from starlette.requests import Request


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: float, now: float) -> float | None:
        """Registra uma requisição. Devolve None se passou, ou quantos segundos esperar."""
        if limit < 1 or window_seconds <= 0:
            raise ValueError("limite e janela precisam ser positivos")
        with self._lock:
            fila = self._hits.setdefault(key, deque())
            while fila and fila[0] <= now - window_seconds:
                fila.popleft()
            if len(fila) >= limit:
                return fila[0] + window_seconds - now
            fila.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter


def client_key(request: Request) -> str:
    """O aluno da sessão, quando há uma; o IP, quando não há. Nunca o token cru."""
    autorizacao = request.headers.get("authorization", "")
    if autorizacao.lower().startswith("bearer "):
        token = autorizacao.split(" ", 1)[1].strip()
        return "sessao:" + hashlib.sha256(token.encode()).hexdigest()
    return "ip:" + (request.client.host if request.client else "desconhecido")


def retry_after(segundos: float) -> str:
    """O cabeçalho Retry-After em segundos inteiros, nunca zero."""
    return str(max(1, math.ceil(segundos)))
