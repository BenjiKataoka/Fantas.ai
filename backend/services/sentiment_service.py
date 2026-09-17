"""
4-pass Gemini player stock analysis pipeline (Player Tracker).

Pass 1 (flash-lite): Historical profile → baseline tier, career summary, ADP assessment
Pass 2 (flash):      News integration → stock direction, news vs history, ADP alignment
Pass 3 (flash):      Concern score → concern_level (1-10), bullish/bearish factors, outlook
Pass 4 (flash-lite): Sentiment → sentiment_score (-1 to 1), worry_score (1-10), contrarian flag

Combined score formula:
  combined_stock_score = (concern_level × 0.50) + (worry_score × 0.30) + (adp_penalty × 0.20)
  adp_penalty: RISING=-1, STABLE=0, FALLING=+2

Never raises — returns None on full failure.
"""
import json
import logging
from typing import Optional

from google import genai

from config import GEMINI_API_KEY, GEMINI_PRIMARY, GEMINI_FALLBACK, LLM_ENABLED
from services import llm_budget

logger = logging.getLogger(__name__)

_genai_client = genai.Client(api_key=GEMINI_API_KEY)

ADP_PENALTY = {"RISING": -1, "STABLE": 0, "FALLING": 2}


# ── Prompts ───────────────────────────────────────────────────────────────────

PASS1_PROMPT = """You are a fantasy football analyst building a player stock profile.

PLAYER: {player_name} | {position} | {nfl_team} | Age: {age} | Exp: {years_exp} yrs
CONTRACT YEAR: {contract_year}

HISTORICAL STATS (last 3 seasons):
{stats_context}

Return ONLY valid JSON (no markdown):
{{
  "historical_context": "<200-word career summary covering trajectory, peak performance, consistency, and key historical signals>",
  "baseline_tier": "<ELITE|HIGH_END_STARTER|MID_TIER_STARTER|FLEX_OPTION|BENCH_STASH|AVOID>",
  "key_historical_signals": ["<signal 1>", "<signal 2>", "<signal 3>"],
  "adp_assessment": "<Is the player drafted at, above, or below their historical value? 1-2 sentences.>"
}}"""


PASS2_PROMPT = """You are a fantasy football analyst integrating recent news with a player's historical profile.

PASS 1 PROFILE:
{pass1_json}

RECENT NEWS SUMMARY (last 2 weeks):
{recent_news}

CURRENT ADP: FFC={ffc_adp}, FantasyPros={fp_adp}
ADP TREND (14-day): {adp_trend} (delta: {adp_delta} positions)
CURRENT WEIGHTED PROJECTION: {weighted_proj} PPR points this week

Return ONLY valid JSON (no markdown):
{{
  "news_summary": "<1-2 sentence summary of the most relevant recent news>",
  "news_vs_history": "<CONSISTENT|CONCERNING|ENCOURAGING|CONTRADICTORY> — does recent news align with historical profile?",
  "stock_direction": "<BULLISH|BEARISH|NEUTRAL>",
  "stock_magnitude": "<HIGH|MEDIUM|LOW>",
  "adp_alignment": "<OVERVALUED|FAIR_VALUE|UNDERVALUED> — given news and history, is current ADP appropriate?",
  "short_term_outlook": "<1-2 sentences on next 4 weeks>",
  "long_term_outlook": "<1-2 sentences on rest of season / offseason>",
  "draft_recommendation": "<EARLY_TARGET|FAIR_VALUE|LATE_ROUND|AVOID|WATCHLIST_ONLY>"
}}"""


PASS3_PROMPT = """You are a fantasy football analyst assigning a concern score to a player.

PASS 1 PROFILE:
{pass1_json}

PASS 2 ANALYSIS:
{pass2_json}

Assign a concern score and explain your reasoning. Higher concern = more risk/uncertainty.

Return ONLY valid JSON (no markdown):
{{
  "concern_level": <1-10 integer — 1=no concerns, 10=major red flags>,
  "concern_summary": "<One direct sentence summarizing the primary concern or strength>",
  "bullish_factors": ["<factor 1>", "<factor 2>"],
  "bearish_factors": ["<factor 1>", "<factor 2>"],
  "injury_risk": "<LOW|MEDIUM|HIGH>",
  "usage_risk": "<LOW|MEDIUM|HIGH>"
}}"""


PASS4_PROMPT = """You are a sentiment analyst reviewing all available signals for a fantasy football player.

FULL ANALYSIS SO FAR:
{all_passes_json}

Assess the overall sentiment and detect any contrarian signals.

Return ONLY valid JSON (no markdown):
{{
  "sentiment_score": <-1.0 to 1.0 — negative=bearish, positive=bullish>,
  "sentiment_label": "<VERY_BULLISH|BULLISH|SLIGHTLY_BULLISH|NEUTRAL|SLIGHTLY_BEARISH|BEARISH|VERY_BEARISH>",
  "dominant_themes": ["<theme 1>", "<theme 2>"],
  "sentiment_vs_stock": "<CONFIRMS|STRENGTHENS|WEAKENS|CONTRADICTS> — does sentiment match the stock direction?",
  "alignment_note": "<1 sentence explaining why sentiment confirms or contradicts the stock direction>",
  "contrarian_flag": <true|false — true if market sentiment appears to be mispricing this player>,
  "worry_score": <1-10 integer — reflects current news-cycle anxiety regardless of long-term outlook>
}}"""


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_full_analysis(
    player_name: str,
    position: str,
    nfl_team: str,
    age: Optional[int],
    years_exp: Optional[int],
    contract_year: bool,
    stats_context: str,
    recent_news: str,
    ffc_adp: Optional[float],
    fp_adp: Optional[float],
    adp_trend: str,
    adp_delta: float,
    weighted_proj: Optional[float],
) -> Optional[dict]:
    """
    Run all 4 Gemini passes and return the combined result dict.

    Returns None if Pass 1 or 2 fail (minimum viable output requires both).
    Pass 3/4 failures degrade gracefully — their fields will be None.
    """
    # Pass 1 — historical profile
    pass1 = await _run_pass(
        PASS1_PROMPT.format(
            player_name=player_name,
            position=position or "N/A",
            nfl_team=nfl_team or "N/A",
            age=age or "Unknown",
            years_exp=years_exp or "Unknown",
            contract_year="Yes" if contract_year else "No",
            stats_context=stats_context or "No historical stats available.",
        ),
        model=GEMINI_PRIMARY,
        pass_num=1,
    )
    if pass1 is None:
        return None

    # Pass 2 — news integration
    pass2 = await _run_pass(
        PASS2_PROMPT.format(
            pass1_json=json.dumps(pass1, indent=2),
            recent_news=recent_news or "No recent news.",
            ffc_adp=ffc_adp or "N/A",
            fp_adp=fp_adp or "N/A",
            adp_trend=adp_trend,
            adp_delta=adp_delta,
            weighted_proj=weighted_proj or "N/A (offseason)",
        ),
        model=GEMINI_FALLBACK,
        pass_num=2,
    )
    if pass2 is None:
        return None

    # Pass 3 — concern score
    pass3 = await _run_pass(
        PASS3_PROMPT.format(
            pass1_json=json.dumps(pass1, indent=2),
            pass2_json=json.dumps(pass2, indent=2),
        ),
        model=GEMINI_FALLBACK,
        pass_num=3,
    )

    # Pass 4 — sentiment
    all_passes = {"pass1": pass1, "pass2": pass2, "pass3": pass3}
    pass4 = await _run_pass(
        PASS4_PROMPT.format(
            all_passes_json=json.dumps(all_passes, indent=2),
        ),
        model=GEMINI_PRIMARY,
        pass_num=4,
    )

    # Compute combined score
    concern_level = (pass3 or {}).get("concern_level") or 5
    worry_score = (pass4 or {}).get("worry_score") or 5
    adp_penalty = ADP_PENALTY.get(adp_trend, 0)
    combined_score = round(
        (concern_level * 0.50) + (worry_score * 0.30) + (adp_penalty * 0.20), 2
    )

    return {
        "pass1": pass1,
        "pass2": pass2,
        "pass3": pass3,
        "pass4": pass4,
        "combined_score": combined_score,
        # Flattened fields for direct DB writes
        "historical_context": pass1.get("historical_context"),
        "baseline_tier": pass1.get("baseline_tier"),
        "overall_direction": pass2.get("stock_direction"),
        "overall_magnitude": pass2.get("stock_magnitude"),
        "short_term_outlook": pass2.get("short_term_outlook"),
        "long_term_outlook": pass2.get("long_term_outlook"),
        "draft_recommendation": pass2.get("draft_recommendation"),
        "concern_level": pass3.get("concern_level") if pass3 else None,
        "concern_summary": pass3.get("concern_summary") if pass3 else None,
        "bullish_factors": pass3.get("bullish_factors") if pass3 else None,
        "bearish_factors": pass3.get("bearish_factors") if pass3 else None,
        "sentiment_score": pass4.get("sentiment_score") if pass4 else None,
        "sentiment_label": pass4.get("sentiment_label") if pass4 else None,
        "dominant_themes": pass4.get("dominant_themes") if pass4 else None,
        "sentiment_vs_stock": pass4.get("sentiment_vs_stock") if pass4 else None,
        "alignment_note": pass4.get("alignment_note") if pass4 else None,
        "contrarian_flag": pass4.get("contrarian_flag", False) if pass4 else False,
        "worry_score": pass4.get("worry_score") if pass4 else None,
    }


# ── Gemini helpers ────────────────────────────────────────────────────────────

async def _run_pass(prompt: str, model: str, pass_num: int) -> Optional[dict]:
    """Call Gemini and parse JSON. Falls back to the other model on failure."""
    result = await _call_gemini(prompt, model)
    if result is None:
        fallback = GEMINI_FALLBACK if model == GEMINI_PRIMARY else GEMINI_PRIMARY
        logger.warning(f"[Sentiment] Pass {pass_num} failed on {model}, trying {fallback}")
        result = await _call_gemini(prompt, fallback)
    if result is None:
        logger.error(f"[Sentiment] Pass {pass_num} failed on both models")
    return result


async def _call_gemini(prompt: str, model: str) -> Optional[dict]:
    text = await _call_gemini_text(prompt, model)
    if not text:
        return None
    try:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        return json.loads(cleaned.strip())
    except json.JSONDecodeError as e:
        logger.error(f"[Sentiment] JSON parse failed ({model}): {e}\nRaw: {text[:300]}")
        return None


async def _call_gemini_text(prompt: str, model: str) -> Optional[str]:
    if not LLM_ENABLED:
        logger.info(f"[Sentiment] LLM disabled (LLM_ENABLED=false) — skipping {model} call")
        return None
    if not llm_budget.can_spend():
        logger.warning(f"[Sentiment] Daily LLM cap reached — skipping {model} call")
        return None
    llm_budget.record_call()
    try:
        response = _genai_client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.error(f"[Sentiment] Gemini call failed ({model}): {e}")
        return None
