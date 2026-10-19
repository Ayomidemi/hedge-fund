"""Preserve signal attempts, record decisions and monitor background execution."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "202610160001"
down_revision = "202610140001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('instruments', sa.Column('execution_metadata', pg.JSONB(), nullable=False, server_default='{}'))
    op.add_column('instruments', sa.Column('metadata_next_attempt_at', sa.DateTime(timezone=True)))
    op.add_column('paper_orders', sa.Column('signal_id', pg.UUID(as_uuid=True)))
    op.execute("""UPDATE paper_orders SET signal_id=(evidence->>'radar_snapshot_id')::uuid
        WHERE evidence->>'radar_snapshot_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'""")
    op.drop_index('uq_paper_order_run_instrument', table_name='paper_orders')
    op.create_index('uq_paper_order_active_instrument', 'paper_orders', ['run_id','instrument_id'], unique=True,
                    postgresql_where=sa.text("status IN ('pending','open')"))
    op.create_index('uq_paper_order_signal', 'paper_orders', ['run_id','instrument_id','signal_id'], unique=True)
    op.create_table('paper_cycle_events',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', pg.UUID(as_uuid=True), sa.ForeignKey('paper_fund_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decisions', pg.JSONB(), nullable=False),
        sa.Column('transitions', pg.JSONB(), nullable=False),
        sa.Column('blockers', pg.JSONB(), nullable=False))
    op.create_index('ix_paper_cycle_run_time','paper_cycle_events',['run_id','recorded_at'])
    op.create_table('worker_heartbeats',
        sa.Column('name', sa.String(32), primary_key=True),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('error_code', sa.String(64)))


def downgrade():
    # A downgrade must never delete repeated trade lifecycles to restore uniqueness.
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM paper_orders GROUP BY run_id,instrument_id
        HAVING count(*)>1) THEN RAISE EXCEPTION 'Cannot downgrade while immutable repeat attempts exist';
        END IF; END $$""")
    op.drop_table('worker_heartbeats')
    op.drop_table('paper_cycle_events')
    op.drop_index('uq_paper_order_signal', table_name='paper_orders')
    op.drop_index('uq_paper_order_active_instrument', table_name='paper_orders')
    op.create_index('uq_paper_order_run_instrument','paper_orders',['run_id','instrument_id'], unique=True)
    op.drop_column('paper_orders','signal_id')
    op.drop_column('instruments','metadata_next_attempt_at')
    op.drop_column('instruments','execution_metadata')
