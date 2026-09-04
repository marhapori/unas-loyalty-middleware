"""make datetime columns timezone-aware

Written by hand: autogenerate produces an empty diff here because SQLite has no
real DateTime-vs-DateTime(timezone=True) distinction at the storage/reflection
level, so it never notices this change - but Postgres does, and defaults to
TIMESTAMP WITHOUT TIME ZONE, which is what caused a real "can't compare
offset-naive and offset-aware datetimes" crash in the worker after switching
Render from SQLite to Postgres (see docs/KNOWN_LIMITATIONS.md, 2026-09-04).

Revision ID: de2c0497de17
Revises: a74d67003c8f
Create Date: 2026-09-04 11:03:48.304769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de2c0497de17'
down_revision: Union[str, Sequence[str], None] = 'a74d67003c8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TZ_DATETIME = sa.DateTime(timezone=True)

# Order matters on SQLite: batch mode recreates the whole table (drop + rename),
# and SQLite enforces FK constraints on that drop - a table with outgoing FKs
# must be recreated before the tables it references, or the DROP of the
# referenced table fails with "FOREIGN KEY constraint failed" (Postgres has no
# such issue; ALTER COLUMN TYPE there is an in-place metadata change).
_COLUMNS = [
    ("webhook_events", ["received_at", "next_attempt_at"]),
    ("loyalty_transactions", ["created_at", "applied_at"]),
    ("loyalty_customers", ["created_at", "updated_at", "last_synced_at"]),
    ("users", ["created_at"]),
]


def upgrade() -> None:
    for table_name, columns in _COLUMNS:
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in columns:
                batch_op.alter_column(column_name, type_=_TZ_DATETIME)


def downgrade() -> None:
    for table_name, columns in _COLUMNS:
        with op.batch_alter_table(table_name) as batch_op:
            for column_name in columns:
                batch_op.alter_column(column_name, type_=sa.DateTime())
