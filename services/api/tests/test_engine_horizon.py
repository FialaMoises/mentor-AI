from __future__ import annotations

from datetime import date, timedelta

from app.engine import (
    DayCapacity,
    EngineParams,
    StudyMode,
    TaskKind,
    TopicState,
    plan_horizon,
    restart_capacities,
)

HOJE = date(2026, 9, 25)
PARAMS = EngineParams()


def temas(quantos: int = 3, **ajustes: object) -> dict[str, TopicState]:
    base = {
        f"t{i}": TopicState(
            topic_id=f"t{i}",
            incidence=1.0 - 0.1 * i,
            self_assessment=0.1 * i,
        )
        for i in range(quantos)
    }
    base.update(ajustes)  # type: ignore[arg-type]
    return base


def dias(quantos: int, minutos: int = 120, **kwargs: object) -> list[DayCapacity]:
    return [
        DayCapacity(HOJE + timedelta(days=d), minutos, **kwargs)  # type: ignore[arg-type]
        for d in range(quantos)
    ]


def test_todo_tema_ganha_teoria_e_questoes_ate_a_prova() -> None:
    plano = plan_horizon(dias(40), temas(3), HOJE + timedelta(days=40), PARAMS)

    for topic_id in temas(3):
        tipos = {t.kind for t in plano.tasks if t.topic_id == topic_id}
        assert {TaskKind.TEORIA, TaskKind.QUESTOES} <= tipos
    assert plano.projection.fits


def test_questoes_nunca_vem_antes_da_teoria_do_mesmo_tema() -> None:
    plano = plan_horizon(dias(40), temas(4), HOJE + timedelta(days=40), PARAMS)

    for topic_id in temas(4):
        teoria = next(
            t.day for t in plano.tasks if t.topic_id == topic_id and t.kind is TaskKind.TEORIA
        )
        questoes = next(
            t.day for t in plano.tasks if t.topic_id == topic_id and t.kind is TaskKind.QUESTOES
        )
        assert teoria <= questoes, f"{topic_id}: questões antes da teoria"


def test_no_mesmo_dia_a_teoria_aparece_antes_das_questoes() -> None:
    plano = plan_horizon(dias(40), temas(1), HOJE + timedelta(days=40), PARAMS)
    do_primeiro_dia = [t for t in plano.tasks if t.day == HOJE]

    assert [t.kind for t in do_primeiro_dia] == [TaskKind.TEORIA, TaskKind.QUESTOES]


def test_cada_tema_estudado_gera_revisoes_em_1_7_e_30_dias() -> None:
    plano = plan_horizon(dias(60), temas(1), HOJE + timedelta(days=60), PARAMS)

    teoria = next(t for t in plano.tasks if t.kind is TaskKind.TEORIA)
    revisoes = sorted(t.day for t in plano.tasks if t.kind is TaskKind.REVISAO)
    assert revisoes == [teoria.day + timedelta(days=offset) for offset in (1, 7, 30)]


def test_tema_ja_estudado_nao_recebe_teoria_de_novo() -> None:
    estudado = TopicState(
        topic_id="t0",
        incidence=1.0,
        self_assessment=0.3,
        studied_on=HOJE - timedelta(days=2),
        reviews_done=1,
    )
    plano = plan_horizon(dias(40), {"t0": estudado}, HOJE + timedelta(days=40), PARAMS)

    assert not [t for t in plano.tasks if t.kind is TaskKind.TEORIA]
    # A revisão de 1 dia já foi feita; sobram as de 7 e 30.
    revisoes = sorted(t.review_index for t in plano.tasks if t.kind is TaskKind.REVISAO)
    assert revisoes == [1, 2]


def test_revisao_vencida_passa_na_frente_da_teoria_nova() -> None:
    atrasado = TopicState(
        topic_id="antigo",
        incidence=0.2,
        self_assessment=0.9,
        studied_on=HOJE - timedelta(days=10),
    )
    entrada = {**temas(2), "antigo": atrasado}
    plano = plan_horizon(dias(30), entrada, HOJE + timedelta(days=30), PARAMS)

    primeiro = [t for t in plano.tasks if t.day == HOJE][0]
    assert primeiro.kind is TaskKind.REVISAO
    assert primeiro.topic_id == "antigo"


def test_dia_leve_nao_recebe_teoria() -> None:
    capacidades = dias(30)
    capacidades[0] = DayCapacity(HOJE, 300, light=True)
    plano = plan_horizon(capacidades, temas(3), HOJE + timedelta(days=30), PARAMS)

    do_dia = {t.kind for t in plano.tasks if t.day == HOJE}
    assert TaskKind.TEORIA not in do_dia


def test_dia_de_prova_secundaria_fica_vazio() -> None:
    capacidades = dias(30)
    capacidades[3] = DayCapacity(HOJE + timedelta(days=3), 0)
    plano = plan_horizon(capacidades, temas(5), HOJE + timedelta(days=30), PARAMS)

    assert not [t for t in plano.tasks if t.day == HOJE + timedelta(days=3)]


def test_nenhum_dia_estoura_a_capacidade() -> None:
    capacidades = dias(20, minutos=100)
    plano = plan_horizon(capacidades, temas(8), HOJE + timedelta(days=20), PARAMS)

    por_dia: dict[date, int] = {}
    for tarefa in plano.tasks:
        por_dia[tarefa.day] = por_dia.get(tarefa.day, 0) + tarefa.minutes
    for capacidade in capacidades:
        assert por_dia.get(capacidade.day, 0) <= capacidade.free_minutes


def test_plano_que_nao_cabe_avisa_e_nao_corta_sozinho() -> None:
    plano = plan_horizon(dias(3, minutos=60), temas(10), HOJE + timedelta(days=3), PARAMS)

    assert plano.projection.fits is False
    assert plano.projection.missing_minutes > 0
    assert plano.unscheduled
    assert plano.projection.extra_minutes_per_day > 0
    # Nada foi removido por conta própria: o que não coube volta na lista.
    agendados = {t.topic_id for t in plano.tasks}
    sem_lugar = {c.topic_id for c in plano.unscheduled}
    assert agendados | sem_lugar == set(temas(10))


def test_temas_sem_lugar_vem_do_menos_prioritario_para_o_mais() -> None:
    plano = plan_horizon(dias(2, minutos=60), temas(6), HOJE + timedelta(days=2), PARAMS)

    sem_lugar = plano.projection.unscheduled_topics
    assert sem_lugar
    # t5 é o de menor incidência e maior autoavaliação: o primeiro a ser oferecido para corte.
    assert sem_lugar[0] == "t5"


def test_plano_que_cabe_nao_sugere_carga_extra() -> None:
    plano = plan_horizon(dias(40), temas(2), HOJE + timedelta(days=40), PARAMS)

    assert plano.projection.fits
    assert plano.projection.extra_minutes_per_day == 0
    assert plano.projection.missing_minutes == 0


def test_mesma_entrada_gera_exatamente_o_mesmo_horizonte() -> None:
    entrada = temas(5)
    primeiro = plan_horizon(dias(15), entrada, HOJE + timedelta(days=15), PARAMS)
    segundo = plan_horizon(
        list(reversed(dias(15))), dict(reversed(list(entrada.items()))), HOJE + timedelta(days=15)
    )

    assert primeiro.tasks == segundo.tasks


def test_modo_cursinho_segue_a_ordem_da_trilha() -> None:
    entrada = temas(3)
    plano = plan_horizon(
        dias(30),
        entrada,
        HOJE + timedelta(days=30),
        PARAMS,
        mode=StudyMode.CURSINHO,
        track=["t2", "t0", "t1"],
    )

    teorias = [t.topic_id for t in plano.tasks if t.kind is TaskKind.TEORIA]
    assert teorias == ["t2", "t0", "t1"]


def test_modo_independente_segue_a_prioridade() -> None:
    plano = plan_horizon(dias(30), temas(3), HOJE + timedelta(days=30), PARAMS)

    teorias = [t.topic_id for t in plano.tasks if t.kind is TaskKind.TEORIA]
    assert teorias == ["t0", "t1", "t2"]


def test_horizonte_sem_dias_uteis_devolve_plano_vazio() -> None:
    plano = plan_horizon([], temas(3), HOJE + timedelta(days=30), PARAMS)

    assert plano.tasks == ()
    assert plano.projection.fits


def test_dias_depois_da_prova_sao_ignorados() -> None:
    plano = plan_horizon(dias(30), temas(2), HOJE + timedelta(days=5), PARAMS)

    assert all(t.day <= HOJE + timedelta(days=5) for t in plano.tasks)


def test_semana_de_retomada_comeca_leve_e_sobe() -> None:
    reduzidos = restart_capacities(dias(10, minutos=200), PARAMS)

    assert reduzidos[0].free_minutes == 100
    assert reduzidos[1].free_minutes == 120
    assert reduzidos[6].free_minutes == 200
    assert reduzidos[7].free_minutes == 200


def test_retomada_nao_empilha_atraso_no_primeiro_dia() -> None:
    capacidades = restart_capacities(dias(30, minutos=200), PARAMS)
    plano = plan_horizon(capacidades, temas(6), HOJE + timedelta(days=30), PARAMS)

    do_primeiro_dia = sum(t.minutes for t in plano.tasks if t.day == HOJE)
    assert do_primeiro_dia <= 100
