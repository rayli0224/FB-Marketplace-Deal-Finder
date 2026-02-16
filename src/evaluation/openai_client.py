"""
Low-level OpenAI API helpers for sync and async requests.

Provides response extraction, JSON parsing, rate-limit retry, and request
creation. Used by ebay_query_generator and ebay_result_filter.
"""

import asyncio
import json
import time
from typing import Any, Optional

try:
    from openai import OpenAI, AsyncOpenAI, RateLimitError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    RateLimitError = Exception  # type: ignore[misc, assignment]

RATE_LIMIT_RETRY_DELAY_SEC = 0.5
RATE_LIMIT_MAX_RETRIES = 3


def extract_response_output_text(response: Any) -> str:
    """
    Extract plain text from an OpenAI Responses API result.

    Uses the convenience output_text when available, then falls back to the
    structured output blocks if needed.
    """
    output_text = (getattr(response, "output_text", "") or "").strip()
    if output_text:
        return output_text

    output_blocks = getattr(response, "output", None) or []
    for message in output_blocks:
        contents = getattr(message, "content", None) or []
        for block in contents:
            text = getattr(block, "text", None)
            if not text:
                continue
            return text.strip()
    return ""


def strip_markdown_code_fences(raw_content: str) -> str:
    """Remove surrounding markdown code fences from model output."""
    content = raw_content.strip()
    if not content:
        return ""

    lines = content.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def try_parse_json_dict(raw_content: str) -> Optional[dict]:
    """
    Parse model output into a JSON object dictionary.

    Returns None when output is empty, invalid JSON, or not a dict.
    """
    content = strip_markdown_code_fences(raw_content)
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_rate_limit_error(e: BaseException) -> bool:
    """True if the exception indicates an OpenAI rate limit (429)."""
    if isinstance(e, RateLimitError) and RateLimitError is not Exception:
        return True
    return getattr(e, "status_code", None) == 429 or "429" in str(e)


def create_sync_response(
    client: "OpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
    model: str = "gpt-5-mini",
) -> Any:
    """
    Create a sync OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) after a short delay.
    """
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            return client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                time.sleep(RATE_LIMIT_RETRY_DELAY_SEC)
            else:
                raise


async def create_async_response(
    client: "AsyncOpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
    model: str = "gpt-5-mini",
) -> Any:
    """
    Create an async OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) after a short delay.
    """
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            return await client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                await asyncio.sleep(RATE_LIMIT_RETRY_DELAY_SEC)
            else:
                raise
