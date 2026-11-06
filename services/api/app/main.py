from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import routers
from .clock import monotonic
from .config import get_settings
from .ratelimit import client_key, get_rate_limiter, retry_after

settings = get_settings()

app = FastAPI(title="mentor-AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

#: Fora do limite: o webhook do provedor (ele reenvia sozinho e é idempotente).
SEM_LIMITE = frozenset({"/api/v1/billing/webhook"})
ESCRITA = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@app.middleware("http")
async def limitar_frequencia(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Limite geral por cliente, e um mais apertado para escrita."""
    caminho = request.url.path
    if not caminho.startswith("/api/") or caminho in SEM_LIMITE or request.method == "OPTIONS":
        return await call_next(request)

    config = get_settings()
    chave = client_key(request)
    agora = monotonic()
    limites = [("geral", config.rate_limit_per_minute)]
    if request.method in ESCRITA:
        limites.append(("escrita", config.rate_limit_writes_per_minute))
    for nome, limite in limites:
        espera = get_rate_limiter().hit(
            f"{nome}:{chave}", limit=limite, window_seconds=60, now=agora
        )
        if espera is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": f"muitas requisições; tente de novo em {retry_after(espera)} s"},
                headers={"Retry-After": retry_after(espera)},
            )
    return await call_next(request)


for router in routers:
    app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
