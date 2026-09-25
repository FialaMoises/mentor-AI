"""documentos, compromissos e consentimento

A rotina do aluno vira compromisso; o arquivo original vira Document com prazo
de retenção. O expurgo apaga o arquivo e mantém o JSON extraído.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25 14:35:53.181807+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("weekly_hours", sa.Integer(), nullable=False, server_default="14")
        )

    op.create_table('consent',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=60), nullable=False),
    sa.Column('policy_version', sa.String(length=20), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('consent', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_consent_student_id'), ['student_id'], unique=False)

    op.create_table('document',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('storage_key', sa.String(length=300), nullable=True),
    sa.Column('content_type', sa.String(length=120), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('extracted', sa.JSON(), nullable=True),
    sa.Column('error', sa.String(length=400), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retention_until', sa.Date(), nullable=True),
    sa.Column('purged_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("kind in ('grade', 'escala', 'cursinho', 'outro')", name='ck_document_kind'),
    sa.CheckConstraint("status in ('recebido', 'extraido', 'confirmado', 'falhou')", name='ck_document_status'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('document', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_student_id'), ['student_id'], unique=False)

    op.create_table('commitment',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=True),
    sa.Column('on_day', sa.Date(), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=True),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.CheckConstraint("kind in ('aula', 'plantao', 'academia', 'trabalho', 'outro')", name='ck_commitment_kind'),
    sa.CheckConstraint('(weekday is null) <> (on_day is null)', name='ck_commitment_recurrence'),
    sa.CheckConstraint('duration_minutes > 0', name='ck_commitment_duration'),
    sa.ForeignKeyConstraint(['document_id'], ['document.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_commitment_student_id'), ['student_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.drop_column("weekly_hours")

    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commitment_student_id'))

    op.drop_table('commitment')
    with op.batch_alter_table('document', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_student_id'))

    op.drop_table('document')
    with op.batch_alter_table('consent', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_consent_student_id'))

    op.drop_table('consent')
