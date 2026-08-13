"""wave07 project phase and relationship resolution fields

Revision ID: 6f9e0d0bf2e7
Revises: 9c2d06a8f1b4
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "6f9e0d0bf2e7"
down_revision = "9c2d06a8f1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("phase_label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("phase_start_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("phase_end_number", sa.Integer(), nullable=True))

    with op.batch_alter_table("project_relationships") as batch_op:
        batch_op.add_column(sa.Column("confidence_score", sa.Numeric(precision=5, scale=4), nullable=True))
        batch_op.add_column(sa.Column("rationale", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "project_relationship_confidence_range",
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_relationships") as batch_op:
        batch_op.drop_constraint("project_relationship_confidence_range", type_="check")
        batch_op.drop_column("rationale")
        batch_op.drop_column("confidence_score")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("phase_end_number")
        batch_op.drop_column("phase_start_number")
        batch_op.drop_column("phase_label")
