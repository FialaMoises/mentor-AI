"""Motor de planejamento do mentor-AI.

Regra da casa: este pacote é puro. Nada aqui importa SQLAlchemy, requests,
boto3, o cliente do LLM ou `datetime.now()`. Quem tem relógio e banco é a
camada de fora.
"""

from .planner import fill_day
from .scoring import priority, proficiency, urgency
from .types import (
    LIGHT_DAY_KINDS,
    Candidate,
    DayCapacity,
    EngineParams,
    PlannedTask,
    TaskKind,
    TopicState,
)

__all__ = [
    "LIGHT_DAY_KINDS",
    "Candidate",
    "DayCapacity",
    "EngineParams",
    "PlannedTask",
    "TaskKind",
    "TopicState",
    "fill_day",
    "priority",
    "proficiency",
    "urgency",
]
