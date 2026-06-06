"""add batch_jobs table and batch columns on outreach_jobs

Revision ID: b1f2c3d4e5a6
Revises: 02045f1ebc6a
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1f2c3d4e5a6'
down_revision: Union[str, None] = '02045f1ebc6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'batch_jobs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('product_profile_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.TEXT(), server_default=sa.text("'running'"), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('research_done', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('personalize_done', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('error_message', sa.TEXT(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name='ck_batch_jobs_status'),
        sa.ForeignKeyConstraint(['product_profile_id'], ['product_profiles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_batch_jobs_user_id_created_at', 'batch_jobs', ['user_id', 'created_at'], unique=False)

    op.add_column('outreach_jobs', sa.Column('batch_id', sa.UUID(), nullable=True))
    op.add_column('outreach_jobs', sa.Column('batch_index', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_outreach_jobs_batch_id', 'outreach_jobs', 'batch_jobs',
        ['batch_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index('ix_outreach_jobs_batch_id', 'outreach_jobs', ['batch_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_outreach_jobs_batch_id', table_name='outreach_jobs')
    op.drop_constraint('fk_outreach_jobs_batch_id', 'outreach_jobs', type_='foreignkey')
    op.drop_column('outreach_jobs', 'batch_index')
    op.drop_column('outreach_jobs', 'batch_id')
    op.drop_index('ix_batch_jobs_user_id_created_at', table_name='batch_jobs')
    op.drop_table('batch_jobs')
