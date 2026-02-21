"""
Low-level OpenAI API helpers for sync and async requests.

Provides response extraction, JSON parsing, rate-limit retry, and request
creation. Used by ebay_query_generator and ebay_results_filter.
"""

import asyncio
import json
import re
import threading
import time
from typing import Any, Optional

try:
    from openai import OpenAI, AsyncOpenAI, RateLimitError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    RateLimitError = Exception  # type: ignore[misc, assignment]

from src.scrapers.fb_marketplace_scraper import SearchCancelledError
from src.utils.search_runtime_config import OPENAI_MAX_CONCURRENT_REQUESTS

RATE_LIMIT_INITIAL_DELAY_SEC = 1.0
RATE_LIMIT_MAX_RETRIES = 5
RATE_LIMIT_BACKOFF_MULTIPLIER = 2.0
RATE_LIMIT_RETRY_BUFFER_SEC = 0.25

# Shared semaphore for limiting concurrent OpenAI API requests (both sync and async)
# Using threading.Semaphore so it works across all threads and event loops
_shared_semaphore: Optional[threading.Semaphore] = None
_shared_semaphore_lock = threading.Lock()


def _get_shared_semaphore() -> threading.Semaphore:
    """Get or create the shared semaphore for limiting concurrent requests across all threads and event loops."""
    global _shared_semaphore
    if _shared_semaphore is None:
        with _shared_semaphore_lock:
            if _shared_semaphore is None:
                _shared_semaphore = threading.Semaphore(OPENAI_MAX_CONCURRENT_REQUESTS)
    return _shared_semaphore


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    """
    Read `key` from either an object attribute or a dict key.

    The OpenAI SDK response types can be either typed objects or plain dicts,
    depending on SDK version and serialization paths.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def extract_response_output_text(response: Any) -> str:
    """
    Extract plain text from an OpenAI Responses API result.

    Uses the convenience output_text property when available, then falls back to
    manually traversing the structured output blocks.
    """
    # Try the convenience property first
    if hasattr(response, "output_text"):
        try:
            output_text = response.output_text
            if output_text and output_text.strip():
                return output_text.strip()
        except Exception:
            pass
    
    # Fallback: manually traverse the output structure
    output_blocks = _get_attr_or_key(response, "output", None) or []
    texts = []
    for output_item in output_blocks:
        # Check if this is a message output item
        item_type = _get_attr_or_key(output_item, "type", None)
        if item_type == "message":
            # Get the content list
            content_list = _get_attr_or_key(output_item, "content", None) or []
            for content_item in content_list:
                # Check if this is a text content item
                content_type = _get_attr_or_key(content_item, "type", None)
                if content_type == "output_text":
                    text = _get_attr_or_key(content_item, "text", None)
                    if text:
                        texts.append(text)
        else:
            # Try to get text directly if it's not a message
            if hasattr(output_item, "text"):
                text = getattr(output_item, "text", None)
                if text:
                    texts.append(text)
            elif isinstance(output_item, dict):
                text = output_item.get("text")
                if text:
                    texts.append(text)
    
    if texts:
        return "".join(texts).strip()
    return ""


def extract_url_citations(response: Any) -> list[dict]:
    """
    Extract URL citations from a Responses API result.

    Returns a list of dicts with url/title when available. This is intended for
    debug logging only; callers should not pass these into other model prompts.
    """
    output_blocks = _get_attr_or_key(response, "output", None) or []
    citations: list[dict] = []

    for output_item in output_blocks:
        if _get_attr_or_key(output_item, "type", None) != "message":
            continue
        content_list = _get_attr_or_key(output_item, "content", None) or []
        for content_item in content_list:
            if _get_attr_or_key(content_item, "type", None) != "output_text":
                continue
            annotations = _get_attr_or_key(content_item, "annotations", None) or []
            for ann in annotations:
                if _get_attr_or_key(ann, "type", None) != "url_citation":
                    continue
                url = _get_attr_or_key(ann, "url", "") or ""
                title = _get_attr_or_key(ann, "title", "") or ""
                if url:
                    citations.append({"url": url, "title": title})

    # Deduplicate while preserving order
    seen = set()
    unique: list[dict] = []
    for c in citations:
        key = (c.get("url", ""), c.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def strip_markdown_code_fences(raw_content: str) -> str:
    """Remove surrounding markdown code fences from model output."""
    text = raw_content.strip()
    if not text:
        return ""
    
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


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


def _try_extract_retry_after_sec(e: BaseException) -> Optional[float]:
    """
    Best-effort extraction of server-suggested wait time for 429s.

    The OpenAI SDK may expose this via a Retry-After header, or embed a
    "Please try again in Xs" hint in the error message.
    """
    # Header-based (if available)
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None) if resp is not None else None
    if headers:
        try:
            retry_after = headers.get("retry-after") or headers.get("Retry-After")
            if retry_after:
                return float(retry_after)
        except Exception:
            pass

    # Message-based fallback
    msg = str(e)
    m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", msg, flags=re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def create_sync_response(
    client: "OpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
    model: str = "gpt-5-mini",
    tools: Optional[list] = None,
    request_overrides: Optional[dict[str, Any]] = None,
    cancelled: Optional[threading.Event] = None,
) -> Any:
    """
    Create a sync OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) with exponential backoff.
    Uses a shared semaphore to limit concurrent requests.
    """
    semaphore = _get_shared_semaphore()
    
    # Acquire semaphore (with cancellation check)
    # Use blocking=True with periodic cancellation checks for better performance
    while True:
        if cancelled and cancelled.is_set():
            raise SearchCancelledError("Search was cancelled by user")
        if semaphore.acquire(blocking=False):
            break
        # Shorter poll interval to reduce latency
        time.sleep(0.01)
    
    try:
        for attempt in range(RATE_LIMIT_MAX_RETRIES):
            if cancelled and cancelled.is_set():
                raise SearchCancelledError("Search was cancelled by user")
            
            try:
                request_kwargs = {
                    "model": model,
                    "instructions": instructions,
                    "input": prompt,
                    "max_output_tokens": max_output_tokens,
                }
                if tools is not None:
                    request_kwargs["tools"] = tools
                if request_overrides:
                    # Only allow plain string keys to avoid hard-to-debug serialization errors.
                    safe_overrides = {str(k): v for k, v in request_overrides.items()}
                    request_kwargs.update(safe_overrides)
                return client.responses.create(
                    **request_kwargs,
                )
            except Exception as e:
                if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    retry_after = _try_extract_retry_after_sec(e)
                    # Exponential backoff: delay = initial_delay * (multiplier ^ attempt)
                    exponential_delay = RATE_LIMIT_INITIAL_DELAY_SEC * (RATE_LIMIT_BACKOFF_MULTIPLIER ** attempt)
                    if retry_after is not None:
                        delay = max(exponential_delay, retry_after + RATE_LIMIT_RETRY_BUFFER_SEC)
                    else:
                        delay = exponential_delay
                    
                    # Poll for cancellation during delay
                    elapsed = 0.0
                    poll_interval = 0.1
                    while elapsed < delay:
                        if cancelled and cancelled.is_set():
                            raise SearchCancelledError("Search was cancelled by user")
                        sleep_time = min(poll_interval, delay - elapsed)
                        time.sleep(sleep_time)
                        elapsed += sleep_time
                else:
                    raise
    finally:
        semaphore.release()


async def create_async_response(
    client: "AsyncOpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
    model: str = "gpt-5-mini",
    cancelled: Optional[threading.Event] = None,
) -> Any:
    """
    Create an async OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) with exponential backoff.
    Uses a shared semaphore to limit concurrent requests.
    """
    semaphore = _get_shared_semaphore()
    
    # Acquire semaphore (with cancellation check)
    # Use asyncio.to_thread to wait on the threading.Semaphore from async context
    # Shorter poll interval to reduce latency
    while True:
        if cancelled and cancelled.is_set():
            raise SearchCancelledError("Search was cancelled by user")
        acquired = await asyncio.to_thread(lambda: semaphore.acquire(blocking=False))
        if acquired:
            break
        await asyncio.sleep(0.01)
    
    try:
        for attempt in range(RATE_LIMIT_MAX_RETRIES):
            if cancelled and cancelled.is_set():
                raise SearchCancelledError("Search was cancelled by user")
            
            try:
                # Wrap the API call in a cancelable task that checks cancellation periodically
                async def _make_request():
                    # Create a task for the API call
                    api_task = asyncio.create_task(
                        client.responses.create(
                            model=model,
                            instructions=instructions,
                            input=prompt,
                            max_output_tokens=max_output_tokens,
                        )
                    )
                    
                    # Poll for cancellation while waiting for the API call
                    while not api_task.done():
                        if cancelled and cancelled.is_set():
                            api_task.cancel()
                            try:
                                await api_task
                            except asyncio.CancelledError:
                                pass
                            raise SearchCancelledError("Search was cancelled by user")
                        await asyncio.sleep(0.1)
                    
                    return await api_task
                
                return await _make_request()
            except SearchCancelledError:
                raise
            except Exception as e:
                if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    retry_after = _try_extract_retry_after_sec(e)
                    # Exponential backoff: delay = initial_delay * (multiplier ^ attempt)
                    exponential_delay = RATE_LIMIT_INITIAL_DELAY_SEC * (RATE_LIMIT_BACKOFF_MULTIPLIER ** attempt)
                    if retry_after is not None:
                        delay = max(exponential_delay, retry_after + RATE_LIMIT_RETRY_BUFFER_SEC)
                    else:
                        delay = exponential_delay
                    
                    # Poll for cancellation during delay
                    elapsed = 0.0
                    poll_interval = 0.1
                    while elapsed < delay:
                        if cancelled and cancelled.is_set():
                            raise SearchCancelledError("Search was cancelled by user")
                        sleep_time = min(poll_interval, delay - elapsed)
                        await asyncio.sleep(sleep_time)
                        elapsed += sleep_time
                else:
                    raise
    finally:
        semaphore.release()
