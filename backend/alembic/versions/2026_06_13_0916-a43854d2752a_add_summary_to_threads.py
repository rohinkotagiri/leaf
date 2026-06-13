"""add_summary_to_threads

Revision ID: a43854d2752a
Revises: b5d774efa819
Create Date: 2026-06-13 09:16:47.860536

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43854d2752a'
down_revision: Union[str, None] = 'b5d774efa819'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('threads', sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('threads', 'summary')
