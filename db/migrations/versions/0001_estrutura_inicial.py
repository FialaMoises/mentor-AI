"""estrutura inicial

Revision ID: 0001
Revises: 
Create Date: 2026-09-24 14:52:56.268380+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('student',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('phase', sa.String(length=20), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('subscription_status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("mode in ('cursinho','independente')", name='ck_student_mode'),
    sa.CheckConstraint("phase in ('faculdade','formado')", name='ck_student_phase'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('topic',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('area', sa.String(length=80), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('parent_id', sa.Uuid(), nullable=True),
    sa.Column('incidence', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['topic.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('daily_capacity',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('free_minutes', sa.Integer(), nullable=False),
    sa.Column('light', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'day', name='uq_capacity_student_day')
    )
    with op.batch_alter_table('daily_capacity', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_daily_capacity_student_id'), ['student_id'], unique=False)

    op.create_table('plan_version',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(length=60), nullable=False),
    sa.Column('summary', sa.String(length=400), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'number', name='uq_plan_version_number')
    )
    with op.batch_alter_table('plan_version', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plan_version_student_id'), ['student_id'], unique=False)

    op.create_table('proficiency',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('self_assessment', sa.Float(), nullable=False),
    sa.Column('answered', sa.Integer(), nullable=False),
    sa.Column('correct', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topic.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'topic_id', name='uq_proficiency_student_topic')
    )
    with op.batch_alter_table('proficiency', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_proficiency_student_id'), ['student_id'], unique=False)

    op.create_table('target_exam',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('exam_date', sa.Date(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('target_exam', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_target_exam_student_id'), ['student_id'], unique=False)

    op.create_table('task',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('plan_version_id', sa.Uuid(), nullable=False),
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('minutes', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.CheckConstraint("kind in ('teoria', 'questoes', 'revisao', 'simulado')", name='ck_task_kind'),
    sa.CheckConstraint("status in ('pendente', 'feita', 'nao_deu')", name='ck_task_status'),
    sa.ForeignKeyConstraint(['plan_version_id'], ['plan_version.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['student.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topic.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_day'), ['day'], unique=False)
        batch_op.create_index(batch_op.f('ix_task_student_id'), ['student_id'], unique=False)

    op.create_table('progress_event',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('answered', sa.Integer(), nullable=True),
    sa.Column('correct', sa.Integer(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint("action in ('feita', 'nao_deu')", name='ck_progress_action'),
    sa.ForeignKeyConstraint(['task_id'], ['task.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('progress_event', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_progress_event_task_id'), ['task_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('progress_event', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_progress_event_task_id'))

    op.drop_table('progress_event')
    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_student_id'))
        batch_op.drop_index(batch_op.f('ix_task_day'))

    op.drop_table('task')
    with op.batch_alter_table('target_exam', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_target_exam_student_id'))

    op.drop_table('target_exam')
    with op.batch_alter_table('proficiency', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_proficiency_student_id'))

    op.drop_table('proficiency')
    with op.batch_alter_table('plan_version', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plan_version_student_id'))

    op.drop_table('plan_version')
    with op.batch_alter_table('daily_capacity', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_daily_capacity_student_id'))

    op.drop_table('daily_capacity')
    op.drop_table('topic')
    op.drop_table('student')
