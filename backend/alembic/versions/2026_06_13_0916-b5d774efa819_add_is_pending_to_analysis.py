"""add_is_pending_to_analysis

Revision ID: b5d774efa819
Revises: aa4cb698c68d
Create Date: 2026-06-13 09:16:04.593868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5d774efa819'
down_revision: Union[str, None] = 'aa4cb698c68d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column with server default '1' (True) for existing records
    op.add_column('email_analyses', sa.Column('is_pending', sa.Boolean(), server_default='1', nullable=False))


def downgrade() -> None:
    op.drop_column('email_analyses', 'is_pending')
