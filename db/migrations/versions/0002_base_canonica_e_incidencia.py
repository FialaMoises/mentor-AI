"""base canônica em três níveis e incidência por prova

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25

A incidência sai de `topic` e vira `topic_incidence`, porque o peso de um tema
depende da prova. Linhas de tema que já existiam (o seed da fase 0) recebem um
slug `legado-<id>`: nada é apagado, e o carregador do catálogo cria os temas
novos com os slugs definitivos.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exam",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("authority", sa.String(length=160), nullable=False),
        sa.Column("notes", sa.String(length=600), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("exam", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_exam_slug"), ["slug"], unique=True)

    op.create_table(
        "topic_incidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=400), nullable=False),
        sa.Column("checked_at", sa.Date(), nullable=True),
        sa.CheckConstraint("weight > 0 and weight <= 1", name="ck_incidence_weight"),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "exam_id", name="uq_incidence_topic_exam"),
    )

    with op.batch_alter_table("target_exam", schema=None) as batch_op:
        batch_op.add_column(sa.Column("exam_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_target_exam_exam_id", "exam", ["exam_id"], ["id"], ondelete="SET NULL"
        )

    # Primeiro nulo, para as linhas existentes não barrarem a migration.
    with op.batch_alter_table("topic", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("level", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("position", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE topic SET slug = 'legado-' || CAST(id AS VARCHAR), "
            "level = 3, position = 0 WHERE slug IS NULL"
        )
    )

    with op.batch_alter_table("topic", schema=None) as batch_op:
        batch_op.alter_column("slug", existing_type=sa.String(length=160), nullable=False)
        batch_op.alter_column("level", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("position", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(batch_op.f("ix_topic_slug"), ["slug"], unique=True)
        batch_op.create_check_constraint("ck_topic_level", "level between 1 and 3")
        batch_op.drop_column("incidence")


def downgrade() -> None:
    with op.batch_alter_table("topic", schema=None) as batch_op:
        batch_op.add_column(sa.Column("incidence", sa.Float(), nullable=False, server_default="1"))
        batch_op.drop_constraint("ck_topic_level", type_="check")
        batch_op.drop_index(batch_op.f("ix_topic_slug"))
        batch_op.drop_column("position")
        batch_op.drop_column("level")
        batch_op.drop_column("slug")

    with op.batch_alter_table("target_exam", schema=None) as batch_op:
        batch_op.drop_constraint("fk_target_exam_exam_id", type_="foreignkey")
        batch_op.drop_column("exam_id")

    op.drop_table("topic_incidence")
    with op.batch_alter_table("exam", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exam_slug"))
    op.drop_table("exam")
