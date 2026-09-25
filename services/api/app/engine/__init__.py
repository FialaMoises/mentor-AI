"""Motor de planejamento do mentor-AI.

Regra da casa: este pacote é puro. Nada aqui importa SQLAlchemy, requests,
boto3, o cliente do LLM ou `datetime.now()`. Quem tem relógio e banco é a
camada de fora.
"""

from .planner import fill_day, plan_horizon, restart_capacities
from .routine import (
    LONG_SHIFT_MINUTES,
    Commitment,
    busy_minutes,
    capacities_from_commitments,
    daily_budget,
)
from .scoring import priority, proficiency, urgency
from .types import (
    KIND_ORDER,
    LIGHT_DAY_KINDS,
    Candidate,
    DayCapacity,
    EngineParams,
    HorizonPlan,
    PlannedTask,
    Projection,
    StudyMode,
    TaskKind,
    TopicState,
)

__all__ = [
    "KIND_ORDER",
    "LONG_SHIFT_MINUTES",
    "LIGHT_DAY_KINDS",
    "Candidate",
    "Commitment",
    "DayCapacity",
    "EngineParams",
    "HorizonPlan",
    "PlannedTask",
    "Projection",
    "StudyMode",
    "TaskKind",
    "TopicState",
    "busy_minutes",
    "capacities_from_commitments",
    "daily_budget",
    "fill_day",
    "plan_horizon",
    "priority",
    "proficiency",
    "restart_capacities",
    "urgency",
]
