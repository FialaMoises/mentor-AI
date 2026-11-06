"""rotina editável: horário de início, série e tipo leitura

O aluno passa a cadastrar compromissos à mão na tela Minha rotina. Cada
compromisso ganha horário de início (para a agenda), a série a que pertence
(os registros de um mesmo compromisso semanal) e a marca de bloco de arquivo
editado pelo aluno. Os compromissos já gravados viram séries de um registro.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NOVOS = "kind in ('aula', 'plantao', 'academia', 'trabalho', 'leitura', 'outro')"
KINDS_ANTIGOS = "kind in ('aula', 'plantao', 'academia', 'trabalho', 'outro')"


def upgrade() -> None:
    with op.batch_alter_table("commitment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("starts_at", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("series_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "edited_by_student", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.create_index(batch_op.f("ix_commitment_series_id"), ["series_id"], unique=False)
        batch_op.drop_constraint("ck_commitment_kind", type_="check")
        batch_op.create_check_constraint("ck_commitment_kind", KINDS_NOVOS)

    op.execute("UPDATE commitment SET series_id = id WHERE series_id IS NULL")

    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.add_column(sa.Column("routine_changed_on", sa.Date(), nullable=True))


def downgrade() -> None:
    conexao = op.get_bind()
    leituras = conexao.execute(
        sa.text("SELECT count(*) FROM commitment WHERE kind = 'leitura'")
    ).scalar_one()
    if leituras:
        raise RuntimeError(
            f"há {leituras} compromissos do tipo 'leitura'; mude o tipo deles antes de voltar"
        )

    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.drop_column("routine_changed_on")

    with op.batch_alter_table("commitment", schema=None) as batch_op:
        batch_op.drop_constraint("ck_commitment_kind", type_="check")
        batch_op.create_check_constraint("ck_commitment_kind", KINDS_ANTIGOS)
        batch_op.drop_index(batch_op.f("ix_commitment_series_id"))
        batch_op.drop_column("edited_by_student")
        batch_op.drop_column("series_id")
        batch_op.drop_column("starts_at")
