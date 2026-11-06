from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.engine import (
    Commitment,
    EngineParams,
    busy_minutes,
    capacities_from_commitments,
    daily_budget,
)

SEGUNDA = date(2026, 9, 28)


def semana() -> list[date]:
    return [SEGUNDA + timedelta(days=d) for d in range(7)]


def test_compromisso_que_cabe_na_janela_nao_derruba_a_meta_do_dia() -> None:
    """Quatro horas de aula ainda deixam as cinco horas de estudo de pé."""
    aula = Commitment(kind="aula", weekday=0, duration_minutes=240)

    dias = capacities_from_commitments(semana(), [aula], 300)

    assert dias[0].free_minutes == 300
    assert dias[1].free_minutes == 300


def test_dia_cheio_corta_a_meta_pelo_que_sobra_do_dia() -> None:
    """Nove horas de enfermaria: sobra uma da janela, e é ela que manda."""
    enfermaria = Commitment(kind="aula", weekday=0, duration_minutes=540)

    dias = capacities_from_commitments(semana(), [enfermaria], 300)

    assert dias[0].free_minutes == 60
    assert dias[1].free_minutes == 300


def test_janela_de_estudo_e_parametro_de_calibracao() -> None:
    enfermaria = Commitment(kind="aula", weekday=0, duration_minutes=540)
    params = EngineParams(study_window_minutes=12 * 60)

    dias = capacities_from_commitments(semana(), [enfermaria], 300, params)

    assert dias[0].free_minutes == 180


def test_compromissos_do_mesmo_dia_somam() -> None:
    aula = Commitment(kind="aula", weekday=2, duration_minutes=360)
    ambulatorio = Commitment(kind="aula", weekday=2, duration_minutes=120)
    academia = Commitment(kind="academia", weekday=2, duration_minutes=60)

    dias = capacities_from_commitments(semana(), [aula, ambulatorio, academia], 300)

    assert dias[2].free_minutes == 60


def test_dia_lotado_nao_fica_com_capacidade_negativa() -> None:
    plantao = Commitment(kind="plantao", weekday=3, duration_minutes=24 * 60)

    dias = capacities_from_commitments(semana(), [plantao], 300)

    assert dias[3].free_minutes == 0


def test_dia_seguinte_a_plantao_longo_e_dia_leve() -> None:
    plantao = Commitment(kind="plantao", weekday=3, duration_minutes=24 * 60)

    dias = capacities_from_commitments(semana(), [plantao], 300)

    assert dias[3].light is False
    assert dias[4].light is True
    assert dias[5].light is False


def test_compromisso_curto_nao_deixa_o_dia_seguinte_leve() -> None:
    academia = Commitment(kind="academia", weekday=3, duration_minutes=60)

    dias = capacities_from_commitments(semana(), [academia], 300)

    assert dias[4].light is False


def test_vigencia_limita_o_compromisso_ao_rodizio() -> None:
    rodizio = Commitment(
        kind="aula",
        weekday=0,
        duration_minutes=240,
        starts_on=SEGUNDA + timedelta(days=7),
    )

    dias = capacities_from_commitments(semana(), [rodizio], 300)

    assert dias[0].free_minutes == 300


def test_compromisso_de_data_unica_vale_so_naquele_dia() -> None:
    plantao = Commitment(kind="plantao", on_day=SEGUNDA + timedelta(days=2), duration_minutes=540)

    dias = capacities_from_commitments(semana(), [plantao], 300)

    assert dias[2].free_minutes == 60
    assert all(d.free_minutes == 300 for d in dias if d.day != plantao.on_day)


def test_compromisso_precisa_ser_semanal_ou_de_data_unica() -> None:
    with pytest.raises(ValueError):
        Commitment(kind="aula", duration_minutes=60)
    with pytest.raises(ValueError):
        Commitment(kind="aula", weekday=0, on_day=SEGUNDA, duration_minutes=60)


def test_compromisso_invalido_nao_e_aceito() -> None:
    with pytest.raises(ValueError):
        Commitment(kind="aula", weekday=9, duration_minutes=60)
    with pytest.raises(ValueError):
        Commitment(kind="aula", weekday=0, duration_minutes=0)
    with pytest.raises(ValueError):
        Commitment(kind="aula", weekday=0, duration_minutes=25 * 60)
    with pytest.raises(ValueError):
        Commitment(
            kind="aula",
            weekday=0,
            duration_minutes=60,
            starts_on=SEGUNDA,
            ends_on=SEGUNDA - timedelta(days=1),
        )


def test_janela_de_estudo_invalida_e_recusada() -> None:
    with pytest.raises(ValueError):
        EngineParams(study_window_minutes=0)
    with pytest.raises(ValueError):
        EngineParams(study_window_minutes=25 * 60)


def test_horas_por_semana_viram_minutos_por_dia() -> None:
    assert daily_budget(14) == 120
    assert daily_budget(0) == 0
    with pytest.raises(ValueError):
        daily_budget(-1)


def test_orcamento_negativo_e_recusado() -> None:
    with pytest.raises(ValueError):
        capacities_from_commitments(semana(), [], -10)


def test_compromisso_encerrado_nao_conta_mais() -> None:
    rodizio = Commitment(
        kind="aula",
        weekday=0,
        duration_minutes=240,
        ends_on=SEGUNDA - timedelta(days=1),
    )

    dias = capacities_from_commitments(semana(), [rodizio], 300)

    assert dias[0].free_minutes == 300


def test_sobreposicao_com_horario_conta_uma_vez() -> None:
    """Academia cadastrada à mão em cima de um bloco do arquivo não desconta em dobro."""
    aula = Commitment(kind="aula", weekday=0, duration_minutes=120, starts_at=time(17, 0))
    academia = Commitment(kind="academia", weekday=0, duration_minutes=75, starts_at=time(18, 0))

    assert busy_minutes([aula, academia], SEGUNDA) == 135  # 17h00–19h15


def test_compromisso_sem_horario_soma_como_antes() -> None:
    aula = Commitment(kind="aula", weekday=0, duration_minutes=120, starts_at=time(17, 0))
    leitura = Commitment(kind="leitura", weekday=0, duration_minutes=60)

    assert busy_minutes([aula, leitura], SEGUNDA) == 180


def test_intervalos_separados_somam() -> None:
    manha = Commitment(kind="aula", weekday=0, duration_minutes=60, starts_at=time(7, 0))
    noite = Commitment(kind="academia", weekday=0, duration_minutes=60, starts_at=time(18, 0))

    assert busy_minutes([manha, noite], SEGUNDA) == 120


def test_intervalo_contido_em_outro_nao_soma() -> None:
    plantao = Commitment(kind="plantao", weekday=0, duration_minutes=720, starts_at=time(7, 0))
    reuniao = Commitment(kind="trabalho", weekday=0, duration_minutes=60, starts_at=time(9, 0))

    assert busy_minutes([plantao, reuniao], SEGUNDA) == 720


def test_plantao_que_atravessa_a_meia_noite_conta_no_dia_em_que_comeca() -> None:
    noturno = Commitment(kind="plantao", weekday=6, duration_minutes=720, starts_at=time(19, 0))

    dias = capacities_from_commitments(semana() + [SEGUNDA + timedelta(days=7)], [noturno], 120)

    assert dias[6].free_minutes == 0
    assert dias[7].free_minutes == 120
    assert dias[7].light
