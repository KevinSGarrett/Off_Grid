"""wave06 decision eligibility on source observations

Revision ID: 9c2d06a8f1b4
Revises: eebb1d156a98
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "9c2d06a8f1b4"
down_revision = "eebb1d156a98"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_observations") as batch_op:
        batch_op.add_column(
            sa.Column("decision_eligible", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("decision_eligibility_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_observations") as batch_op:
        batch_op.drop_column("decision_eligibility_reason")
        batch_op.drop_column("decision_eligible")
