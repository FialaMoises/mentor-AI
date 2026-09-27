"""Configuração vira parâmetro de calibração.

O motor é puro: não lê `.env`, não lê relógio, não lê banco. Quem traduz o que
está configurado em `EngineParams` é esta borda — e é por aqui que a calibração
muda sem tocar em código.
"""

from __future__ import annotations

from .config import get_settings
from .engine import EngineParams


def engine_params() -> EngineParams:
    settings = get_settings()
    return EngineParams(
        k=settings.engine_k,
        review_offsets_days=settings.review_offsets,
        inactivity_days=settings.engine_inactivity_days,
        study_window_minutes=settings.engine_study_window_minutes,
    )
