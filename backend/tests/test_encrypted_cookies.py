"""
ESPN cookies are encrypted at rest (models.user.EncryptedString).

The things worth pinning: the database only ever holds ciphertext, the app still reads
plain values, and a value that will not decrypt degrades to "not connected" instead of
raising, because the user row loads on every request and a raise would lock them out.

Run: venv/bin/python tests/test_encrypted_cookies.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from cryptography.fernet import Fernet

import models.user as user_model
from config import DATABASE_URL
from database import AsyncSessionLocal
from models.user import EncryptedString, User

FAKE_S2 = "AEB-test-cookie-not-real%2Fabc123"
FAKE_SWID = "{00000000-0000-0000-0000-000000000000}"


def test_round_trip_and_none():
    t = EncryptedString()
    stored = t.process_bind_param(FAKE_S2, None)
    assert stored != FAKE_S2 and stored.startswith("gAAAAA"), "not a Fernet token"
    assert t.process_result_value(stored, None) == FAKE_S2
    assert t.process_bind_param(None, None) is None and t.process_result_value(None, None) is None
    print("  PASS, encrypts to a Fernet token, decrypts back, None stays None")


def test_wrong_key_reads_as_disconnected():
    t = EncryptedString()
    stored = t.process_bind_param(FAKE_S2, None)
    real = user_model.ESPN_COOKIE_KEY
    user_model.ESPN_COOKIE_KEY = Fernet.generate_key().decode()   # a rotated or lost key
    try:
        assert t.process_result_value(stored, None) is None, "wrong key should read as None"
        # A legacy plaintext row must not raise either.
        assert t.process_result_value("plain-legacy-value", None) is None
    finally:
        user_model.ESPN_COOKIE_KEY = real
    print("  PASS, a wrong key or plaintext row reads as None instead of raising")


def test_database_holds_only_ciphertext():
    """Write through the ORM, read it back through a fresh session, then look at the raw
    column without the ORM. One event loop for the async half: two asyncio.run calls
    would hand a pooled asyncpg connection to a closed loop (see CLAUDE.md)."""
    from database import engine

    async def write_then_read():
        async with AsyncSessionLocal() as db:
            u = User(clerk_id="encrypt-test", email="et@example.invalid", username="encrypt-test",
                     is_approved=True, weight_sleeper=0.35, weight_espn=0.30, weight_fp=0.35,
                     espn_s2=FAKE_S2, swid=FAKE_SWID)
            db.add(u)
            await db.commit()
            uid = u.id
        async with AsyncSessionLocal() as db:
            back = await db.get(User, uid)
            result = uid, (back.espn_s2, back.swid)
        await engine.dispose()
        return result

    uid, read_back = asyncio.run(write_then_read())
    conn = psycopg2.connect(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"), sslmode="require")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT espn_s2, swid FROM users WHERE id = %s", (uid,))
        raw_s2, raw_swid = cur.fetchone()
        assert FAKE_S2 not in raw_s2 and FAKE_SWID not in raw_swid, "plaintext reached the database"
        assert raw_s2.startswith("gAAAAA") and raw_swid.startswith("gAAAAA")
        assert read_back == (FAKE_S2, FAKE_SWID), "the app did not read plain values back"
        print(f"  PASS, the raw column holds a {len(raw_s2)}-char token, the app reads the plain value")
    finally:
        cur.execute("DELETE FROM users WHERE id = %s", (uid,))
        conn.close()


if __name__ == "__main__":
    for t in (test_round_trip_and_none, test_wrong_key_reads_as_disconnected, test_database_holds_only_ciphertext):
        print(t.__name__)
        t()
    print("\nAll encrypted cookie tests passed.")
