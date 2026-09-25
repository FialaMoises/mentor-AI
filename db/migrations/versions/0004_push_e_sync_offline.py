"""push, log de notificação e sincronização offline

A marcação feita sem sinal carrega um id do navegador: reenviar a mesma marcação
não vira dois eventos de progresso.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25 15:04:48.573087+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=255), nullable=True))

    op.create_table('notification_log',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('delivered', sa.Boolean(), nullable=False),
    sa.Column('detail', sa.String(length=300), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("channel in ('push', 'email')", name='ck_notification_channel'),
    sa.CheckConstraint("kind in ('lista_do_dia', 'aviso_de_estouro', 'recomeco')", name='ck_notification_kind'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'kind', 'day', name='uq_notification_student_kind_day')
    )
    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_log_day'), ['day'], unique=False)
        batch_op.create_index(batch_op.f('ix_notification_log_student_id'), ['student_id'], unique=False)

    op.create_table('push_subscription',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('endpoint', sa.String(length=600), nullable=False),
    sa.Column('p256dh', sa.String(length=200), nullable=False),
    sa.Column('auth', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint')
    )
    with op.batch_alter_table('push_subscription', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscription_student_id'), ['student_id'], unique=False)

    with op.batch_alter_table('progress_event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('client_event_id', sa.Uuid(), nullable=True))
        batch_op.create_unique_constraint("uq_progress_client_event", ["client_event_id"])



def downgrade() -> None:
    with op.batch_alter_table("student", schema=None) as batch_op:
        batch_op.drop_column("email")

    with op.batch_alter_table('progress_event', schema=None) as batch_op:
        batch_op.drop_constraint("uq_progress_client_event", type_="unique")
        batch_op.drop_column('client_event_id')

    with op.batch_alter_table('push_subscription', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_subscription_student_id'))

    op.drop_table('push_subscription')
    with op.batch_alter_table('notification_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_log_student_id'))
        batch_op.drop_index(batch_op.f('ix_notification_log_day'))

    op.drop_table('notification_log')
