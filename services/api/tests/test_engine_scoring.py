from datetime import date, timedelta

import pytest

from app.engine import EngineParams, TopicState, priority, proficiency, urgency

HOJE = date(2026, 9, 24)
PROVA = HOJE + timedelta(days=120)
PARAMS = EngineParams()


def tema(**kwargs: object) -> TopicState:
    base = {"topic_id": "t", "incidence": 1.0, "self_assessment": 0.5}
    base.update(kwargs)
    return TopicState(**base)  # type: ignore[arg-type]


def test_sem_questoes_a_proficiencia_e_a_autoavaliacao() -> None:
    assert proficiency(tema(self_assessment=0.4), PARAMS) == pytest.approx(0.4)


def test_autoavaliacao_vale_como_k_questoes() -> None:
    # k = 10, autoavaliação 1.0 e 10 questões com 0 acertos: metade do caminho.
    estado = tema(self_assessment=1.0, answered=10, correct=0)
    assert proficiency(estado, PARAMS) == pytest.approx(0.5)


def test_com_muitas_questoes_a_autoavaliacao_perde_peso() -> None:
    estado = tema(self_assessment=1.0, answered=1000, correct=300)
    assert proficiency(estado, PARAMS) == pytest.approx(0.307, abs=0.002)


def test_urgencia_sobe_conforme_a_prova_se_aproxima() -> None:
    longe = urgency(tema(), HOJE, HOJE + timedelta(days=300), PARAMS)
    perto = urgency(tema(), HOJE, HOJE + timedelta(days=10), PARAMS)
    assert perto > longe


def test_urgencia_sobe_com_revisao_vencida_e_tem_teto() -> None:
    sem_atraso = urgency(tema(), HOJE, PROVA, PARAMS)
    atrasado = urgency(tema(review_due_days=7), HOJE, PROVA, PARAMS)
    muito_atrasado = urgency(tema(review_due_days=90), HOJE, PROVA, PARAMS)
    assert atrasado == pytest.approx(sem_atraso + 0.5)
    assert muito_atrasado == pytest.approx(sem_atraso + 1.0)


def test_tema_dominado_perde_prioridade_para_tema_fraco() -> None:
    fraco = priority(tema(topic_id="a", self_assessment=0.1), HOJE, PROVA, PARAMS)
    dominado = priority(tema(topic_id="b", self_assessment=0.95), HOJE, PROVA, PARAMS)
    assert fraco > dominado


def test_incidencia_zero_zera_a_prioridade() -> None:
    assert priority(tema(incidence=0.0), HOJE, PROVA, PARAMS) == 0.0


def test_estado_invalido_nao_e_aceito() -> None:
    with pytest.raises(ValueError):
        tema(self_assessment=1.5)
    with pytest.raises(ValueError):
        tema(answered=3, correct=5)


def test_k_precisa_ser_positivo() -> None:
    with pytest.raises(ValueError):
        EngineParams(k=0)


def test_prova_ja_passou_mantem_a_urgencia_no_teto() -> None:
    assert urgency(tema(), HOJE, HOJE - timedelta(days=1), PARAMS) == pytest.approx(2.0)


def test_horizonte_precisa_ser_positivo() -> None:
    with pytest.raises(ValueError):
        EngineParams(exam_horizon_days=0)


def test_questoes_negativas_nao_sao_aceitas() -> None:
    with pytest.raises(ValueError):
        tema(answered=-1)
