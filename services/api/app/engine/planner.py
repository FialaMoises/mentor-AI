"""Preenchimento do dia e do horizonte até a prova.

Heurística gulosa por prioridade, determinística: a mesma entrada devolve
exatamente o mesmo plano, em qualquer ordem de chegada das listas.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta

from .scoring import priority
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


def fill_day(
    capacity: DayCapacity,
    candidates: list[Candidate],
    topics: Mapping[str, TopicState],
    exam_date: date,
    params: EngineParams | None = None,
) -> list[PlannedTask]:
    """Enche a capacidade de um dia com as tarefas de maior prioridade.

    O desempate é por tipo (revisão, teoria, questões, simulado) e depois por
    tema — nunca pela ordem de chegada da lista.
    """
    params = params or EngineParams()

    for candidate in candidates:
        if candidate.topic_id not in topics:
            raise KeyError(f"tema sem estado: {candidate.topic_id}")

    allowed = [
        candidate
        for candidate in candidates
        if not capacity.light or candidate.kind in LIGHT_DAY_KINDS
    ]

    scored = [(priority(topics[c.topic_id], capacity.day, exam_date, params), c) for c in allowed]
    scored.sort(key=lambda pair: (-pair[0], KIND_ORDER[pair[1].kind], pair[1].topic_id))

    plan: list[PlannedTask] = []
    remaining = capacity.free_minutes
    for score, candidate in scored:
        if candidate.minutes > remaining:
            continue
        remaining -= candidate.minutes
        plan.append(
            PlannedTask(
                day=capacity.day,
                topic_id=candidate.topic_id,
                kind=candidate.kind,
                minutes=candidate.minutes,
                priority=score,
            )
        )
    return plan


def _topic_order(
    topics: Mapping[str, TopicState],
    day: date,
    exam_date: date,
    params: EngineParams,
    mode: StudyMode,
    track: Sequence[str],
) -> list[str]:
    """No modo cursinho a teoria segue a trilha; no independente, a prioridade."""
    by_priority = sorted(
        topics,
        key=lambda topic_id: (-priority(topics[topic_id], day, exam_date, params), topic_id),
    )
    if mode is not StudyMode.CURSINHO:
        return by_priority

    na_trilha = [topic_id for topic_id in track if topic_id in topics]
    fora = [topic_id for topic_id in by_priority if topic_id not in set(na_trilha)]
    return na_trilha + fora


def plan_horizon(
    capacities: Sequence[DayCapacity],
    topics: Mapping[str, TopicState],
    exam_date: date,
    params: EngineParams | None = None,
    *,
    mode: StudyMode = StudyMode.INDEPENDENTE,
    track: Sequence[str] = (),
) -> HorizonPlan:
    """Monta o plano do primeiro dia livre até a prova.

    Cada tema rende uma teoria (se ainda não estudado), um bloco de questões
    depois dela e as revisões dos `review_offsets_days`. Revisão vencida passa
    na frente; dia leve não recebe teoria; o que não couber até a prova volta em
    `unscheduled`, com a projeção do que falta.
    """
    params = params or EngineParams()
    dias = sorted((c for c in capacities if c.day <= exam_date), key=lambda c: c.day)
    if not dias:
        return HorizonPlan(
            tasks=(),
            unscheduled=(),
            projection=Projection(
                fits=True,
                planned_minutes=0,
                available_minutes=0,
                missing_minutes=0,
                days_left=0,
            ),
        )

    inicio = dias[0].day
    ordem = _topic_order(topics, inicio, exam_date, params, mode, track)

    pendentes: list[Candidate] = []
    revisoes: list[tuple[date, str, int]] = []
    teoria_em: dict[str, date] = {}

    for topic_id in ordem:
        estado = topics[topic_id]
        if estado.studied_on is None:
            pendentes.append(
                Candidate(topic_id, TaskKind.TEORIA, params.minutes_for(TaskKind.TEORIA))
            )
        else:
            teoria_em[topic_id] = estado.studied_on
            for índice, offset in enumerate(params.review_offsets_days):
                if índice < estado.reviews_done:
                    continue
                revisoes.append((estado.studied_on + timedelta(days=offset), topic_id, índice))
        pendentes.append(
            Candidate(topic_id, TaskKind.QUESTOES, params.minutes_for(TaskKind.QUESTOES))
        )

    tarefas: list[PlannedTask] = []

    for capacidade in dias:
        restante = capacidade.free_minutes
        dia = capacidade.day

        # 1. Revisões vencidas ou do dia passam na frente de tudo.
        vencidas = sorted((r for r in revisoes if r[0] <= dia), key=lambda r: (r[0], r[2], r[1]))
        for vencida in vencidas:
            minutos = params.minutes_for(TaskKind.REVISAO)
            if minutos > restante:
                continue
            _, topic_id, índice = vencida
            restante -= minutos
            revisoes.remove(vencida)
            tarefas.append(
                PlannedTask(
                    day=dia,
                    topic_id=topic_id,
                    kind=TaskKind.REVISAO,
                    minutes=minutos,
                    priority=priority(topics[topic_id], dia, exam_date, params),
                    review_index=índice,
                )
            )

        # 2. Teoria e questões, na ordem definida pelo modo.
        for candidato in list(pendentes):
            if capacidade.light and candidato.kind not in LIGHT_DAY_KINDS:
                continue
            if candidato.kind is TaskKind.QUESTOES:
                estudado_em = teoria_em.get(candidato.topic_id)
                if estudado_em is None or estudado_em > dia:
                    continue
            if candidato.minutes > restante:
                continue

            restante -= candidato.minutes
            pendentes.remove(candidato)
            tarefas.append(
                PlannedTask(
                    day=dia,
                    topic_id=candidato.topic_id,
                    kind=candidato.kind,
                    minutes=candidato.minutes,
                    priority=priority(topics[candidato.topic_id], dia, exam_date, params),
                )
            )
            if candidato.kind is TaskKind.TEORIA:
                teoria_em[candidato.topic_id] = dia
                for índice, offset in enumerate(params.review_offsets_days):
                    revisoes.append((dia + timedelta(days=offset), candidato.topic_id, índice))

    planejado = sum(t.minutes for t in tarefas)
    disponível = sum(c.free_minutes for c in dias)
    faltando = sum(c.minutes for c in pendentes)
    sem_lugar = tuple(
        dict.fromkeys(c.topic_id for c in reversed(pendentes))
    )  # do menos prioritário para o mais prioritário

    return HorizonPlan(
        tasks=tuple(tarefas),
        unscheduled=tuple(pendentes),
        projection=Projection(
            fits=not pendentes,
            planned_minutes=planejado,
            available_minutes=disponível,
            missing_minutes=faltando,
            days_left=len(dias),
            unscheduled_topics=sem_lugar,
        ),
    )


def restart_capacities(
    capacities: Sequence[DayCapacity], params: EngineParams | None = None
) -> list[DayCapacity]:
    """Semana de retomada: o aluno volta com carga reduzida, subindo aos poucos.

    Sem pilha de atrasos: o que ficou para trás é redistribuído pelo
    replanejamento comum, já com os dias mais leves.
    """
    params = params or EngineParams()
    dias = sorted(capacities, key=lambda c: c.day)
    saída: list[DayCapacity] = []
    for índice, capacidade in enumerate(dias):
        if índice >= params.restart_days:
            saída.append(capacidade)
            continue
        fator = min(1.0, params.restart_floor + params.restart_step * índice)
        saída.append(capacidade.with_minutes(int(capacidade.free_minutes * fator)))
    return saída
