"""
2-pass Gemini news analysis pipeline, runs for starred players only.

Pass 1 (GEMINI_PRIMARY, flash-lite):
  Input: raw news + player context + weighted projection + Sleeper trending + snap/target stats
  Output: summary, news_type, stock_direction, stock_magnitude, short_term_impact,
          long_term_impact, key_factors, confidence_score, needs_context_check

Pass 2 (GEMINI_FALLBACK, flash, only when needs_context_check=True):
  Input: Pass 1 JSON + 500-word rolling news_history_context for this player
  Output: context_notes, contradictions_flagged, contradiction_detail, final_confidence

After each item: regenerate 500-word rolling context summary and store in news_history_context.
HIGH magnitude is only surfaced when news directly states playing status / contract / depth chart
AND confidence_score >= 0.75.
"""

import json
import logging
from datetime import datetime
from typing import Optional


from services.utils import WRITING_STYLE, strip_dashes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import GEMINI_PRIMARY, GEMINI_FALLBACK
from services import gemini_client
from models.news import NewsAnalysis, NewsHistoryContext, PlayerNews

logger = logging.getLogger(__name__)


# ── Pass 1 prompt ──────────────────────────────────────────────────────────────

PASS1_PROMPT = """You are a fantasy football analyst. Analyze this NFL news item and return ONLY valid JSON.

PLAYER: {player_name} | {position} | {nfl_team}
WEIGHTED PROJECTION THIS WEEK: {weighted_proj} PPR points
SLEEPER TRENDING: {trending_status}
RECENT STATS CONTEXT: {stats_context}

NEWS HEADLINE: {headline}
NEWS BODY: {news_body}

Return this exact JSON schema (no markdown, no explanation):
{{
  "summary": "<2-3 sentence plain English summary of what this means for fantasy>",
  "news_type": "<INJURY|CONTRACT|PERFORMANCE|DEPTH_CHART|TRANSACTION|GENERAL>",
  "stock_direction": "<BULLISH|BEARISH|NEUTRAL>",
  "stock_magnitude": "<HIGH|MEDIUM|LOW>",
  "short_term_impact": "<impact on next 1-2 weeks>",
  "long_term_impact": "<impact beyond 2 weeks, or null if not applicable>",
  "key_factors": ["<factor 1>", "<factor 2>"],
  "confidence_score": <0.0 to 1.0>,
  "needs_context_check": <true|false>
}}

Rules:
- stock_magnitude HIGH only if news directly states playing status, contract decision, or depth chart change AND you are confident (>=0.75).
- needs_context_check=true if this news seems to contradict prior reports, if injury timeline is unclear, or if context from the last 2 weeks would materially change the analysis.
- confidence_score reflects how certain you are given the information provided."""


PASS2_PROMPT = """You are a fantasy football analyst reviewing a news item with historical context.

PASS 1 ANALYSIS:
{pass1_json}

RECENT NEWS HISTORY FOR THIS PLAYER (last ~500 words):
{history_context}

Return ONLY valid JSON (no markdown):
{{
  "context_notes": "<how prior news context changes or confirms the Pass 1 analysis>",
  "contradictions_flagged": <true|false>,
  "contradiction_detail": "<what specifically contradicts, or null>",
  "final_confidence": <0.0 to 1.0>
}}"""


CONTEXT_REGENERATION_PROMPT = """Summarize the following recent news items for {player_name} in 500 words or less.
Focus on: injury timeline, depth chart status, contract situation, recent performance trends.
Be factual and concise. This summary will be used as context for future AI analysis.

NEWS ITEMS (most recent first):
{news_items}

Return only the summary text, no JSON."""


# ── Main entry point ───────────────────────────────────────────────────────────

async def analyze_news_item(
    news_item: PlayerNews,
    player_context: dict,
    db: AsyncSession,
) -> Optional[NewsAnalysis]:
    """
    Run the 2-pass Gemini pipeline for a single starred player news item.

    player_context keys:
      player_name, position, nfl_team, weighted_proj (float|None),
      trending_status (str), stats_context (str)

    Returns a NewsAnalysis ORM object (not yet committed, caller commits).
    Returns None if Gemini fails entirely.
    """
    # Pass 1
    pass1 = await _run_pass1(news_item, player_context)
    if pass1 is None:
        logger.error(f"[NewsAnalysis] Pass 1 failed for news_id={news_item.id}")
        return None

    # Enforce HIGH magnitude rule
    if pass1.get("stock_magnitude") == "HIGH" and pass1.get("confidence_score", 0) < 0.75:
        pass1["stock_magnitude"] = "MEDIUM"

    # Pass 2, only when needs_context_check=True
    context_notes = None
    contradictions_flagged = False
    contradiction_detail = None
    final_confidence = pass1.get("confidence_score")
    analysis_model = GEMINI_PRIMARY

    if pass1.get("needs_context_check"):
        history = await _get_history_context(news_item.player_id, db)
        if history:
            pass2 = await _run_pass2(pass1, history)
            if pass2:
                context_notes = pass2.get("context_notes")
                contradictions_flagged = pass2.get("contradictions_flagged", False)
                contradiction_detail = pass2.get("contradiction_detail")
                final_confidence = pass2.get("final_confidence", final_confidence)
                analysis_model = f"{GEMINI_PRIMARY}+{GEMINI_FALLBACK}"

    analysis = NewsAnalysis(
        news_id=news_item.id,
        player_id=news_item.player_id,
        summary=pass1.get("summary"),
        stock_direction=pass1.get("stock_direction"),
        stock_magnitude=pass1.get("stock_magnitude"),
        confidence_score=final_confidence,
        short_term_impact=pass1.get("short_term_impact"),
        long_term_impact=pass1.get("long_term_impact"),
        context_notes=context_notes,
        contradictions_flagged=contradictions_flagged,
        contradiction_detail=contradiction_detail,
        analysis_model=analysis_model,
        generated_at=datetime.utcnow(),
    )

    # Regenerate rolling context summary after every analysis
    await _update_history_context(news_item.player_id, player_context["player_name"], db)

    return analysis


# ── Pass 1 ─────────────────────────────────────────────────────────────────────

async def _run_pass1(news_item: PlayerNews, ctx: dict) -> Optional[dict]:
    prompt = PASS1_PROMPT.format(
        player_name=ctx.get("player_name", "Unknown"),
        position=ctx.get("position", "N/A"),
        nfl_team=ctx.get("nfl_team", "N/A"),
        weighted_proj=ctx.get("weighted_proj") or "N/A",
        trending_status=ctx.get("trending_status") or "Not trending",
        stats_context=ctx.get("stats_context") or "No recent stats available",
        headline=news_item.headline,
        news_body=news_item.news_body or "(no body)",
    )

    result = await gemini_client.call_json(prompt, GEMINI_PRIMARY, "NewsAnalysis")
    if result is None:
        # Fallback to flash
        result = await gemini_client.call_json(prompt, GEMINI_FALLBACK, "NewsAnalysis")
    return result


# ── Pass 2 ─────────────────────────────────────────────────────────────────────

async def _run_pass2(pass1_result: dict, history_context: str) -> Optional[dict]:
    prompt = PASS2_PROMPT.format(
        pass1_json=json.dumps(pass1_result, indent=2),
        history_context=history_context,
    )
    # Pass 2 always uses flash (more capable for contradiction detection)
    result = await gemini_client.call_json(prompt, GEMINI_FALLBACK, "NewsAnalysis")
    return result


# ── Context helpers ────────────────────────────────────────────────────────────

async def _get_history_context(player_id: str, db: AsyncSession) -> Optional[str]:
    stmt = select(NewsHistoryContext).where(NewsHistoryContext.player_id == player_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row.context_summary if row else None


async def _update_history_context(player_id: str, player_name: str, db: AsyncSession) -> None:
    """
    Pull the last 10 news items for this player and regenerate the rolling
    500-word context summary. Upserts into news_history_context.
    """
    stmt = (
        select(PlayerNews)
        .where(PlayerNews.player_id == player_id)
        .order_by(PlayerNews.published_at.desc().nullslast())
        .limit(10)
    )
    result = await db.execute(stmt)
    recent_news = result.scalars().all()

    if not recent_news:
        return

    news_text = "\n\n".join(
        f"[{n.published_at or 'unknown date'}] {n.headline}\n{n.news_body or ''}"
        for n in recent_news
    )

    prompt = CONTEXT_REGENERATION_PROMPT.format(
        player_name=player_name,
        news_items=news_text[:4000],  # cap input to avoid token blowout
    )

    # Use flash-lite for context regeneration, cheap and sufficient
    summary = await gemini_client.call_text(prompt, GEMINI_PRIMARY, "NewsAnalysis")
    if not summary:
        return

    # Upsert
    stmt = select(NewsHistoryContext).where(NewsHistoryContext.player_id == player_id)
    result = await db.execute(stmt)
    ctx_row = result.scalar_one_or_none()

    if ctx_row:
        ctx_row.context_summary = summary[:2000]
        ctx_row.last_updated = datetime.utcnow()
    else:
        db.add(NewsHistoryContext(
            player_id=player_id,
            context_summary=summary[:2000],
        ))

    await db.flush()


# ── Gemini helpers ─────────────────────────────────────────────────────────────

