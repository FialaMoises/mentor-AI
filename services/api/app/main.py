from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import routers
from .config import get_settings

settings = get_settings()

app = FastAPI(title="mentor-AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

for router in routers:
    app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
