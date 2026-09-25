"""autenticação por link mágico e assinatura

O e-mail do aluno vira identidade: passa a ser único. Token de login e sessão
vivem no banco só como hash.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25 16:39:58.645754+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('login_token',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('login_token', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_token_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_token_token_hash'), ['token_hash'], unique=True)

    op.create_table('payment_event',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('external_id', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'external_id', name='uq_payment_event_provider_external')
    )
    op.create_table('auth_session',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('auth_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_auth_session_student_id'), ['student_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_auth_session_token_hash'), ['token_hash'], unique=True)

    op.create_table('subscription',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('plan', sa.String(length=20), nullable=False),
    sa.Column('price_cents', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('provider_ref', sa.String(length=120), nullable=False),
    sa.Column('trial_ends_on', sa.Date(), nullable=True),
    sa.Column('current_period_end', sa.Date(), nullable=True),
    sa.Column('paused_until', sa.Date(), nullable=True),
    sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("plan in ('mensal', 'anual')", name='ck_subscription_plan'),
    sa.CheckConstraint("status in ('trial', 'ativa', 'pausada', 'atrasada', 'cancelada')", name='ck_subscription_status'),
    sa.CheckConstraint('price_cents >= 0', name='ck_subscription_price'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subscription', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscription_student_id'), ['student_id'], unique=True)

    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_student_email'), ['email'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('student', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_student_email'))

    with op.batch_alter_table('subscription', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscription_student_id'))

    op.drop_table('subscription')
    with op.batch_alter_table('auth_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_auth_session_token_hash'))
        batch_op.drop_index(batch_op.f('ix_auth_session_student_id'))

    op.drop_table('auth_session')
    op.drop_table('payment_event')
    with op.batch_alter_table('login_token', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_token_token_hash'))
        batch_op.drop_index(batch_op.f('ix_login_token_email'))

    op.drop_table('login_token')
