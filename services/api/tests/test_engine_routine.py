from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine import Commitment, capacities_from_commitments, daily_budget

SEGUNDA = date(2026, 9, 28)


def semana() -> list[date]:
    return [SEGUNDA + timedelta(days=d) for d in range(7)]


def test_compromisso_semanal_desconta_so_no_dia_da_semana() -> None:
    aula = Commitment(kind="aula", weekday=0, duration_minutes=240)

    dias = capacities_from_commitments(semana(), [aula], 300)

    assert dias[0].free_minutes == 60
    assert dias[1].free_minutes == 300


def test_compromissos_do_mesmo_dia_somam() -> None:
    aula = Commitment(kind="aula", weekday=2, duration_minutes=180)
    academia = Commitment(kind="academia", weekday=2, duration_minutes=60)

    dias = capacities_from_commitments(semana(), [aula, academia], 300)

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
    prova = Commitment(kind="aula", on_day=SEGUNDA + timedelta(days=2), duration_minutes=180)

    dias = capacities_from_commitments(semana(), [prova], 300)

    assert dias[2].free_minutes == 120
    assert all(d.free_minutes == 300 for d in dias if d.day != prova.on_day)


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
