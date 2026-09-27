"""A rotina de mentira que responde quando não há chave do modelo.

Sem `ANTHROPIC_API_KEY` ninguém lê o arquivo — mas o resto do fluxo (conferir a
semana, recalcular capacidade, replanejar) merece ser testável. Este dublê
devolve a rotina da aluna fictícia dos arquivos de `exemplos/`, escolhida pelo
tipo que o aluno declarou no upload, e avisa em `unreadable` que não leu nada.

O aviso é obrigatório: a tela de conferência mostra a lista de `unreadable`, e é
lá que o aluno descobre que aquilo não saiu do arquivo dele.
"""

from __future__ import annotations

from typing import Any

AVISO = (
    "Nada aqui saiu do seu arquivo: o leitor de arquivos não está configurado "
    "(ANTHROPIC_API_KEY). Isto é uma rotina de exemplo, para testar a tela."
)

FACULDADE: list[dict[str, Any]] = [
    {
        "kind": "aula",
        "label": "Clínica Médica — enfermaria",
        "weekday": dia,
        "duration_minutes": 360,
        "ends_on": "2026-12-18",
    }
    for dia in range(5)
] + [
    {
        "kind": "aula",
        "label": "Ambulatório de Pediatria",
        "weekday": 1,
        "duration_minutes": 240,
        "ends_on": "2026-12-18",
    },
    {
        "kind": "aula",
        "label": "Discussão de casos",
        "weekday": 3,
        "duration_minutes": 120,
        "ends_on": "2026-12-18",
    },
]

PLANTOES: list[dict[str, Any]] = [
    {"kind": "plantao", "label": f"Plantão — {setor}", "on_day": dia, "duration_minutes": 720}
    for dia, setor in [
        ("2026-10-03", "PS adulto"),
        ("2026-10-11", "PS adulto"),
        ("2026-10-16", "PS pediátrico"),
        ("2026-10-24", "PS adulto"),
        ("2026-10-27", "PS adulto"),
        ("2026-10-31", "PS adulto"),
    ]
]

CURSINHO: list[dict[str, Any]] = [
    {
        "kind": "aula",
        "label": "Cursinho — aula ao vivo",
        "weekday": 5,
        "duration_minutes": 240,
        "starts_on": "2026-09-05",
        "ends_on": "2026-11-15",
    },
    {
        "kind": "aula",
        "label": "Cursinho — revisão guiada",
        "weekday": 6,
        "duration_minutes": 120,
        "starts_on": "2026-09-05",
        "ends_on": "2026-11-15",
    },
]

FORA_DA_FACULDADE: list[dict[str, Any]] = [
    {"kind": "trabalho", "label": "Monitoria de Semiologia", "weekday": 1, "duration_minutes": 120},
    {"kind": "trabalho", "label": "Aulas particulares", "weekday": 5, "duration_minutes": 180},
    {"kind": "academia", "label": "Musculação", "weekday": 0, "duration_minutes": 75},
    {"kind": "academia", "label": "Musculação", "weekday": 2, "duration_minutes": 75},
    {"kind": "academia", "label": "Musculação", "weekday": 4, "duration_minutes": 75},
    {"kind": "academia", "label": "Corrida leve", "weekday": 6, "duration_minutes": 60},
]

POR_TIPO: dict[str, list[dict[str, Any]]] = {
    "grade": FACULDADE,
    "escala": PLANTOES,
    "cursinho": CURSINHO,
    "outro": FORA_DA_FACULDADE,
}

PROVA = [{"name": "ENAMED 2026", "exam_date": "2026-11-22"}]


def demo_routine(kind: str) -> dict[str, Any]:
    return {
        "commitments": POR_TIPO.get(kind, FORA_DA_FACULDADE),
        "exams": PROVA if kind in ("cursinho", "grade") else [],
        "unreadable": [AVISO],
    }
