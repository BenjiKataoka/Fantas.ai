"""One Gemini client and one call path for every pipeline.

The news and sentiment pipelines each carried their own copy of this, and the copies
drifted: only the sentiment one passed response_mime_type, so the news pipeline was
still exposed to the markdown-fenced JSON parse failures that fix was written for.
"""
import json
import logging
from typing import Optional

from google import genai

from config import GEMINI_API_KEY, LLM_ENABLED
from services import llm_budget
from services.utils import WRITING_STYLE, strip_dashes

logger = logging.getLogger(__name__)

_genai_client = genai.Client(api_key=GEMINI_API_KEY)


async def call_text(prompt: str, model: str, tag: str, json_mode: bool = False) -> Optional[str]:
    """Raw text from Gemini. Returns None when the LLM is disabled, the daily budget for
    this model is spent, or the call fails. `tag` is the log prefix, e.g. "Sentiment".

    json_mode forces response_mime_type so the model emits a bare JSON object instead of
    a fenced block; leave it off for prose, such as the rolling news context summary.
    """
    if not LLM_ENABLED:
        logger.info(f"[{tag}] LLM disabled (LLM_ENABLED=false), skipping {model} call")
        return None
    if not llm_budget.can_spend(model):
        logger.warning(f"[{tag}] Daily budget exhausted for {model}, skipping call")
        return None
    llm_budget.record_call(model)
    try:
        # .aio = the SDK's async client; the sync call blocks the whole event loop for the
        # seconds Gemini takes, stalling every other request during a roster run.
        config = {"response_mime_type": "application/json"} if json_mode else None
        response = await _genai_client.aio.models.generate_content(
            model=model,
            contents=prompt + WRITING_STYLE,
            config=config,
        )
        return strip_dashes(response.text)
    except Exception as e:
        logger.error(f"[{tag}] Gemini call failed ({model}): {e}")
        return None


async def call_json(prompt: str, model: str, tag: str) -> Optional[dict]:
    """A Gemini call that must come back as a JSON object. Returns None on failure.

    Still strips a markdown fence before parsing: response_mime_type makes one unlikely,
    not impossible.
    """
    text = await call_text(prompt, model, tag, json_mode=True)
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
        logger.error(f"[{tag}] JSON parse failed ({model}): {e}\nRaw: {text[:300]}")
        return None
