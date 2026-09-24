from datetime import date, timedelta

import pytest

from app.engine import Candidate, DayCapacity, EngineParams, TaskKind, TopicState, fill_day

HOJE = date(2026, 9, 24)
PROVA = HOJE + timedelta(days=120)
PARAMS = EngineParams()

TEMAS = {
    "fraco": TopicState(topic_id="fraco", incidence=0.9, self_assessment=0.1),
    "medio": TopicState(topic_id="medio", incidence=0.6, self_assessment=0.5),
    "forte": TopicState(topic_id="forte", incidence=0.4, self_assessment=0.95),
}


def candidatos(minutes: int = 60) -> list[Candidate]:
    return [
        Candidate(topic_id=topic_id, kind=kind, minutes=minutes)
        for topic_id in TEMAS
        for kind in (TaskKind.TEORIA, TaskKind.QUESTOES)
    ]


def test_nao_estoura_a_capacidade_do_dia() -> None:
    plano = fill_day(DayCapacity(HOJE, free_minutes=150), candidatos(60), TEMAS, PROVA, PARAMS)
    assert sum(t.minutes for t in plano) <= 150


def test_o_tema_mais_fraco_e_de_maior_incidencia_entra_primeiro() -> None:
    plano = fill_day(DayCapacity(HOJE, free_minutes=120), candidatos(60), TEMAS, PROVA, PARAMS)
    assert plano[0].topic_id == "fraco"


def test_dia_leve_recebe_so_revisao_e_questoes() -> None:
    entrada = [
        Candidate(topic_id="fraco", kind=TaskKind.TEORIA, minutes=50),
        Candidate(topic_id="fraco", kind=TaskKind.QUESTOES, minutes=30),
        Candidate(topic_id="medio", kind=TaskKind.REVISAO, minutes=20),
        Candidate(topic_id="medio", kind=TaskKind.SIMULADO, minutes=180),
    ]
    plano = fill_day(DayCapacity(HOJE, free_minutes=300, light=True), entrada, TEMAS, PROVA, PARAMS)
    assert {t.kind for t in plano} <= {TaskKind.QUESTOES, TaskKind.REVISAO}


def test_dia_sem_capacidade_nao_recebe_tarefa() -> None:
    plano = fill_day(DayCapacity(HOJE, free_minutes=0), candidatos(30), TEMAS, PROVA, PARAMS)
    assert plano == []


def test_tarefa_maior_que_o_dia_e_pulada_sem_quebrar_o_plano() -> None:
    entrada = [
        Candidate(topic_id="fraco", kind=TaskKind.SIMULADO, minutes=300),
        Candidate(topic_id="medio", kind=TaskKind.QUESTOES, minutes=30),
    ]
    plano = fill_day(DayCapacity(HOJE, free_minutes=60), entrada, TEMAS, PROVA, PARAMS)
    assert [t.kind for t in plano] == [TaskKind.QUESTOES]


def test_mesma_entrada_gera_exatamente_o_mesmo_plano() -> None:
    capacidade = DayCapacity(HOJE, free_minutes=180)
    primeiro = fill_day(capacidade, candidatos(50), TEMAS, PROVA, PARAMS)
    embaralhado = list(reversed(candidatos(50)))
    segundo = fill_day(capacidade, embaralhado, TEMAS, PROVA, PARAMS)
    assert primeiro == segundo


def test_candidato_sem_estado_do_tema_falha_alto() -> None:
    with pytest.raises(KeyError):
        fill_day(
            DayCapacity(HOJE, free_minutes=60),
            [Candidate(topic_id="desconhecido", kind=TaskKind.TEORIA, minutes=30)],
            TEMAS,
            PROVA,
            PARAMS,
        )


def test_capacidade_negativa_nao_e_aceita() -> None:
    with pytest.raises(ValueError):
        DayCapacity(HOJE, free_minutes=-10)


def test_tarefa_sem_duracao_nao_e_aceita() -> None:
    with pytest.raises(ValueError):
        Candidate(topic_id="fraco", kind=TaskKind.TEORIA, minutes=0)
