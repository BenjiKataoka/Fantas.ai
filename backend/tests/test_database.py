"""
Verify the Neon database connection works and all expected tables exist.
Usage: python test_database.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPECTED_TABLES = [
    "players",
    "users",
    "user_leagues",
    "projections",
    "my_roster",
    "player_news",
    "news_analysis",
    "news_history_context",
    "beat_writer_sentiment",
    "tracked_players",
    "player_historical_stats",
    "player_adp_history",
    "player_stock_profile",
]


async def run_tests():
    print("=" * 50)
    print("DATABASE CONNECTION TEST")
    print("=" * 50)

    # Test 1: Engine creates without error
    print("\n[1] Creating async engine...")
    try:
        from database import engine, AsyncSessionLocal
        print("    PASS, engine created")
    except Exception as e:
        print(f"    FAIL, {e}")
        return

    # Test 2: Can connect to Neon
    print("\n[2] Testing connection to Neon...")
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            val = result.scalar()
            assert val == 1
        print("    PASS, connected to Neon successfully")
    except Exception as e:
        print(f"    FAIL, {e}")
        return

    # Test 3: All expected tables exist
    print("\n[3] Checking all tables exist in Neon...")
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
            )
            existing = {row[0] for row in result.fetchall()}

        missing = [t for t in EXPECTED_TABLES if t not in existing]
        extra = [t for t in existing if t not in EXPECTED_TABLES and t != "alembic_version"]

        if not missing:
            print(f"    PASS, all {len(EXPECTED_TABLES)} tables present:")
            for t in sorted(EXPECTED_TABLES):
                print(f"           ✓ {t}")
        else:
            print(f"    FAIL, missing tables: {missing}")
            print("           Run: alembic upgrade head")

        if extra:
            print(f"    NOTE, unexpected tables found (not a problem): {extra}")

    except Exception as e:
        print(f"    FAIL, {e}")

    # Test 4: Can write and read a row (players table)
    print("\n[4] Testing write + read on players table...")
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            # Insert a test player
            await session.execute(text("""
                INSERT INTO players (player_id, name, position, nfl_team)
                VALUES ('TEST_001', 'Test Player', 'QB', 'TST')
                ON CONFLICT (player_id) DO NOTHING
            """))
            await session.commit()

            # Read it back
            result = await session.execute(
                text("SELECT name, position FROM players WHERE player_id = 'TEST_001'")
            )
            row = result.fetchone()
            assert row is not None
            assert row[0] == "Test Player"

            # Clean up
            await session.execute(
                text("DELETE FROM players WHERE player_id = 'TEST_001'")
            )
            await session.commit()

        print("    PASS, write and read successful, test row cleaned up")
    except Exception as e:
        print(f"    FAIL, {e}")

    print("\n" + "=" * 50)
    print("DATABASE TEST COMPLETE")
    print("=" * 50)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_tests())
