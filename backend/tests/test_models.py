"""
Verify all SQLAlchemy models import correctly and have expected columns.
Usage: python test_models.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_columns(model, expected_cols: list[str]) -> tuple[bool, list[str]]:
    actual = {c.key for c in model.__table__.columns}
    missing = [c for c in expected_cols if c not in actual]
    return len(missing) == 0, missing


def run_tests():
    print("=" * 50)
    print("MODELS TEST")
    print("=" * 50)

    # Test 1: All models import
    print("\n[1] Importing all models...")
    try:
        from models import (
            Player, User, UserLeague, Projection, MyRoster,
            PlayerNews, NewsAnalysis, NewsHistoryContext, BeatWriterSentiment,
            TrackedPlayer, PlayerHistoricalStats, PlayerADPHistory, PlayerStockProfile,
        )
        print("    PASS — all 13 models imported")
    except Exception as e:
        print(f"    FAIL — {e}")
        return

    # Test 2: Check key columns on each model
    print("\n[2] Checking model columns...")

    checks = [
        (Player, ["player_id", "name", "position", "nfl_team", "sleeper_id",
                  "espn_id", "espn_athlete_id", "fp_name", "injury_status"]),
        (User, ["id", "clerk_id", "email", "username", "is_approved",
                "sleeper_username", "espn_s2", "swid",
                "weight_sleeper", "weight_espn", "weight_fp"]),
        (UserLeague, ["id", "user_id", "platform", "league_id",
                      "league_name", "total_rosters", "season", "is_primary"]),
        (Projection, ["player_id", "week", "season", "sleeper_proj",
                      "espn_proj", "fp_proj", "weighted_proj",
                      "sources_used", "confidence_flag"]),
        (MyRoster, ["user_id", "player_id", "is_starter", "slot"]),
        (PlayerNews, ["player_id", "source", "headline", "news_body",
                      "news_type", "analysis_status", "is_rostered"]),
        (NewsAnalysis, ["news_id", "player_id", "summary", "stock_direction",
                        "stock_magnitude", "confidence_score",
                        "contradictions_flagged", "analysis_model"]),
        (NewsHistoryContext, ["player_id", "context_summary"]),
        (BeatWriterSentiment, ["player_id", "source_name", "sentiment"]),
        (TrackedPlayer, ["user_id", "player_id", "contract_year",
                         "depth_chart_pos", "is_active"]),
        (PlayerHistoricalStats, ["player_id", "season", "fantasy_pts_ppr",
                                  "fantasy_ppg_ppr", "snap_pct_avg"]),
        (PlayerADPHistory, ["player_id", "source", "adp", "overall_rank"]),
        (PlayerStockProfile, ["player_id", "user_id", "concern_level",
                               "worry_score", "combined_score",
                               "sentiment_score", "contrarian_flag",
                               "draft_recommendation"]),
    ]

    all_passed = True
    for model, expected in checks:
        ok, missing = check_columns(model, expected)
        name = model.__tablename__
        if ok:
            print(f"    PASS — {name}")
        else:
            print(f"    FAIL — {name} missing columns: {missing}")
            all_passed = False

    # Test 3: Table names match expected
    print("\n[3] Checking table names...")
    expected_tables = {
        "players", "users", "user_leagues", "projections", "my_roster",
        "player_news", "news_analysis", "news_history_context",
        "beat_writer_sentiment", "tracked_players",
        "player_historical_stats", "player_adp_history", "player_stock_profile"
    }
    from models import (
        Player, User, UserLeague, Projection, MyRoster,
        PlayerNews, NewsAnalysis, NewsHistoryContext, BeatWriterSentiment,
        TrackedPlayer, PlayerHistoricalStats, PlayerADPHistory, PlayerStockProfile,
    )
    actual_tables = {
        m.__tablename__ for m in [
            Player, User, UserLeague, Projection, MyRoster,
            PlayerNews, NewsAnalysis, NewsHistoryContext, BeatWriterSentiment,
            TrackedPlayer, PlayerHistoricalStats, PlayerADPHistory, PlayerStockProfile,
        ]
    }
    missing_tables = expected_tables - actual_tables
    if not missing_tables:
        print(f"    PASS — all 13 table names correct")
    else:
        print(f"    FAIL — missing table names: {missing_tables}")

    print("\n" + "=" * 50)
    print("MODELS TEST COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
