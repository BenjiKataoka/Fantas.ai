"""Encrypt ESPN cookies at rest

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-24

No schema change: both columns are unbounded VARCHAR, and a Fernet token fits. This only
rewrites the stored values, which models.user.EncryptedString now encrypts and decrypts.
Idempotent: a value that already decrypts under the key is left alone, so a rerun or a
row written by the new code is never double-encrypted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet, InvalidToken

from config import ESPN_COOKIE_KEY

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("espn_s2", "swid")


def _fernet() -> Fernet:
    if not ESPN_COOKIE_KEY:
        raise RuntimeError("Set ESPN_COOKIE_KEY before running this migration.")
    return Fernet(ESPN_COOKIE_KEY.encode())


def _is_token(f: Fernet, value: str) -> bool:
    try:
        f.decrypt(value.encode())
        return True
    except InvalidToken:
        return False


def upgrade() -> None:
    f, conn = _fernet(), op.get_bind()
    rows = conn.execute(sa.text("SELECT id, espn_s2, swid FROM users WHERE espn_s2 IS NOT NULL OR swid IS NOT NULL")).all()
    for row in rows:
        values = {c: getattr(row, c) for c in COLUMNS}
        new = {c: (f.encrypt(v.encode()).decode() if v is not None and not _is_token(f, v) else v)
               for c, v in values.items()}
        if new != values:
            conn.execute(sa.text("UPDATE users SET espn_s2 = :espn_s2, swid = :swid WHERE id = :id"),
                         {**new, "id": row.id})


def downgrade() -> None:
    f, conn = _fernet(), op.get_bind()
    rows = conn.execute(sa.text("SELECT id, espn_s2, swid FROM users WHERE espn_s2 IS NOT NULL OR swid IS NOT NULL")).all()
    for row in rows:
        plain = {}
        for c in COLUMNS:
            v = getattr(row, c)
            try:
                plain[c] = None if v is None else f.decrypt(v.encode()).decode()
            except InvalidToken:
                plain[c] = v   # already plaintext
        conn.execute(sa.text("UPDATE users SET espn_s2 = :espn_s2, swid = :swid WHERE id = :id"),
                     {**plain, "id": row.id})
