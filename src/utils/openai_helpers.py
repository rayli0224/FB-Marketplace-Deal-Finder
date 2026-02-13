"""
OpenAI API helper functions for query generation and result filtering.

Provides helper functions for making OpenAI API calls to generate optimized eBay
search queries and filter eBay results to match Facebook Marketplace listings.
"""

import os
import json
import time
import asyncio
from typing import Optional, Tuple, List, Any
import threading

try:
    from openai import OpenAI, AsyncOpenAI, RateLimitError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    RateLimitError = Exception  # type: ignore[misc, assignment]

from src.scrapers.fb_marketplace_scraper import Listing, SearchCancelledError
from src.utils.colored_logger import setup_colored_logger, log_error_short, truncate_lines
from src.utils.prompts import (
    QUERY_GENERATION_SYSTEM_MESSAGE,
    RESULT_FILTERING_SYSTEM_MESSAGE,
    get_query_generation_prompt,
    get_pre_filtering_prompt,
    get_batch_filtering_prompt,
)

logger = setup_colored_logger("openai_helpers")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-5-mini"
PRE_FILTER_MAX_OUTPUT_TOKENS = 300
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000
BATCH_FILTER_MAX_OUTPUT_TOKENS = 3000
POST_FILTER_BATCH_SIZE = 10
RATE_LIMIT_RETRY_DELAY_SEC = 0.5
RATE_LIMIT_MAX_RETRIES = 3

PRE_FILTER_SYSTEM_MESSAGE = "You are an expert at evaluating product listings. Always respond with valid JSON only."


def _format_fb_listing(listing: Listing) -> str:
    """
    Format a FB listing as text for prompts.
    Includes title, price, location (if available), and description (if available).
    """
    listing_text = f"Facebook Marketplace listing:\n- Title: {listing.title}\n- Price: ${listing.price:.2f}"
    if listing.location:
        listing_text += f"\n- Location: {listing.location}"
    if listing.description:
        listing_text += f"\n- Description: {listing.description}"
    return listing_text


def _extract_response_output_text(response: Any) -> str:
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


def _strip_markdown_code_fences(raw_content: str) -> str:
    """
    Remove surrounding markdown code fences from model output.
    """
    content = raw_content.strip()
    if not content:
        return ""

    lines = content.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _try_parse_json_dict(raw_content: str) -> Optional[dict]:
    """
    Parse model output into a JSON object dictionary.

    Returns None when output is empty, invalid JSON, or not a dict.
    """
    content = _strip_markdown_code_fences(raw_content)
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


def _create_sync_response(
    client: "OpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
) -> Any:
    """
    Create a sync OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) after a short delay.
    """
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            return client.responses.create(
                model=OPENAI_MODEL,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                logger.debug(f"Rate limit hit, waiting {RATE_LIMIT_RETRY_DELAY_SEC}s before retry ({attempt + 1}/{RATE_LIMIT_MAX_RETRIES})")
                time.sleep(RATE_LIMIT_RETRY_DELAY_SEC)
            else:
                raise


async def _create_async_response(
    client: "AsyncOpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
) -> Any:
    """
    Create an async OpenAI Responses API request with shared defaults.
    Retries on rate limit (429) after a short delay.
    """
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            return await client.responses.create(
                model=OPENAI_MODEL,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < RATE_LIMIT_MAX_RETRIES - 1:
                logger.debug(f"Rate limit hit, waiting {RATE_LIMIT_RETRY_DELAY_SEC}s before retry ({attempt + 1}/{RATE_LIMIT_MAX_RETRIES})")
                await asyncio.sleep(RATE_LIMIT_RETRY_DELAY_SEC)
            else:
                raise


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str
) -> Optional[Tuple[Optional[str], Optional[dict], Optional[str]]]:
    """
    Generate an optimized eBay search query and optional Browse API parameters for a FB listing.
    Returns (enhanced_query, browse_api_parameters, skip_reason) or None on generic failure.
    On success: (query, params, None). On model rejection: (None, None, reason). On other failure: None.
    """
    if not OpenAI:
        logger.error("Search suggestions unavailable (required package not installed).")
        return None
    if not OPENAI_API_KEY:
        logger.warning("Search suggestions not available (missing configuration).")
        return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    fb_listing_text = _format_fb_listing(listing)
    
    pre_filtering_prompt = get_pre_filtering_prompt(fb_listing_text)
    pre_filtering_response = _create_sync_response(
        client,
        instructions=PRE_FILTER_SYSTEM_MESSAGE,
        prompt=pre_filtering_prompt,
        max_output_tokens=PRE_FILTER_MAX_OUTPUT_TOKENS,
    )
    pre_raw = _extract_response_output_text(pre_filtering_response)
    pre_result = _try_parse_json_dict(pre_raw)
    if isinstance(pre_result, dict) and pre_result.get("rejected"):
        logger.info(f"Pre-filter rejected — {pre_result.get('reason', 'insufficient information')}")
        return None, None, pre_result.get("reason", "insufficient information")
    if isinstance(pre_result, dict):
        logger.info(f"Pre-filter accepted — {pre_result.get('reason', '')}")
    else:
        logger.debug(f"Pre-filter response could not be parsed (raw length {len(pre_raw or '')}), proceeding with query")
    
    prompt = get_query_generation_prompt(fb_listing_text)

    try:
        response = _create_sync_response(
            client,
            instructions=QUERY_GENERATION_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=QUERY_GENERATION_MAX_OUTPUT_TOKENS,
        )
        raw_content = _extract_response_output_text(response)
        try:
            truncated_content = truncate_lines(raw_content, 5)
            logger.debug(f"eBay search suggestion (preview):\n\t{truncated_content}")
        except Exception as e:
            logger.debug(f"Could not show preview: {e}")

        result = _try_parse_json_dict(raw_content)
        if result is None:
            log_error_short(logger, "Search suggestion response was invalid JSON")
            logger.debug(f"Response content: {raw_content}")
            return None

        enhanced_query = result.get("enhanced_query", original_query)
        browse_api_parameters = result.get("browse_api_parameters")
        if not isinstance(browse_api_parameters, dict):
            browse_api_parameters = None
        else:
            # Remove `filter: conditionIds:{{1000|3000}}` from the browse_api_parameters for now
            browse_api_parameters = {k: v for k, v in browse_api_parameters.items() if k != "filter"}
        logger.debug(f"Search: '{enhanced_query}'")
        return (enhanced_query, browse_api_parameters, None)
    except Exception as e:
        log_error_short(logger, f"Search suggestion request failed: {e}")
        return None


def _format_ebay_batch(items: List[dict]) -> str:
    """
    Format a batch of eBay items as text for the batch filtering prompt.
    Items are numbered 1-based within the batch.
    """
    parts = []
    for i, item in enumerate(items):
        title = item.get('title', '')
        price = item.get('price', 0)
        description = item.get('description', '')
        condition = item.get('condition', '')
        local_num = i + 1
        line = f"{local_num}. {title} - ${price:.2f}"
        if condition:
            line += f" | Condition: {condition}"
        if description:
            desc_preview = description[:200] + "..." if len(description) > 200 else description
            line += f"\n   Description: {desc_preview}"
        parts.append(line)
    return "\n".join(parts)


def _try_parse_results_list(raw_content: str, expected_count: int) -> Optional[List[dict]]:
    """
    Parse batch filter response into a list of result dicts.
    Expects a JSON array of objects with rejected and reason. Returns None if invalid.
    """
    content = _strip_markdown_code_fences(raw_content)
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or len(parsed) != expected_count:
        return None
    if not all(isinstance(x, dict) for x in parsed):
        return None
    return parsed


async def _filter_batch(
    client: "AsyncOpenAI",
    fb_listing_text: str,
    items: List[dict],
    start_index: int,
) -> List[Tuple[int, bool, str]]:
    """
    Filter a batch of eBay items against a FB listing using OpenAI.

    start_index: 1-based global index of the first item in this batch.
    Returns list of (1-based global index, rejected, reason) for each item.
    On API error or invalid response, keeps all items in the batch (fail-open).
    """
    if not items:
        return []
    ebay_items_text = _format_ebay_batch(items)
    prompt = get_batch_filtering_prompt(
        fb_listing_text=fb_listing_text,
        ebay_items_text=ebay_items_text,
    )
    try:
        response = await _create_async_response(
            client,
            instructions=RESULT_FILTERING_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=BATCH_FILTER_MAX_OUTPUT_TOKENS,
        )
        raw_content = _extract_response_output_text(response)
        if not raw_content:
            logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: empty response — keeping all")
            return [(start_index + i, False, "") for i in range(len(items))]
        results_list = _try_parse_results_list(raw_content, len(items))
        if results_list is None:
            logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: invalid JSON — keeping all")
            return [(start_index + i, False, "") for i in range(len(items))]
        out = []
        for i, r in enumerate(results_list):
            if not isinstance(r, dict):
                out.append((start_index + i, False, ""))
                continue
            rejected = bool(r.get("rejected", False))
            reason = r.get("reason", "")
            if not isinstance(reason, str):
                reason = str(reason)
            out.append((start_index + i, rejected, reason))
        return out
    except Exception as e:
        logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: API error ({e}) — keeping all")
        return [(start_index + i, False, "") for i in range(len(items))]


async def _filter_ebay_results_async(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[dict], dict]]:
    """
    Async implementation of eBay result filtering using batched API calls.

    Chunks items into batches of POST_FILTER_BATCH_SIZE and runs one async
    OpenAI call per batch in parallel. Aggregates results into the same format
    as the original single-call version.
    """
    if not AsyncOpenAI:
        logger.debug("Async OpenAI unavailable — skipping match filter")
        return None
    if not OPENAI_API_KEY:
        logger.debug("Search suggestions not configured — skipping match filter")
        return None

    if not ebay_items:
        return ([], ebay_items, {})

    if cancelled and cancelled.is_set():
        raise SearchCancelledError("Search was cancelled by user")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = _format_fb_listing(listing)

    batches = []
    for i in range(0, len(ebay_items), POST_FILTER_BATCH_SIZE):
        batch = ebay_items[i : i + POST_FILTER_BATCH_SIZE]
        start_index = i + 1
        batches.append((batch, start_index))

    tasks = [
        asyncio.create_task(_filter_batch(client, fb_listing_text, batch, start_index))
        for batch, start_index in batches
    ]
    try:
        while True:
            done, pending = await asyncio.wait(tasks, timeout=0.5, return_when=asyncio.ALL_COMPLETED)
            if not pending:
                break
            if cancelled and cancelled.is_set():
                for t in pending:
                    t.cancel()
                raise SearchCancelledError("Search was cancelled by user")
        results = []
        for t in tasks:
            results.extend(t.result())
    except asyncio.CancelledError:
        for t in tasks:
            if not t.done():
                t.cancel()
        raise
    
    # Aggregate results
    comparable_indices = []
    reasons = {}
    
    for item_index, rejected, reason in results:
        reasons[str(item_index)] = reason
        if not rejected:
            comparable_indices.append(item_index)
    
    # Sort comparable_indices to maintain order
    comparable_indices.sort()
    
    # Filter items (indices are 1-based, convert to 0-based)
    filtered_items = [
        ebay_items[idx - 1]
        for idx in comparable_indices
        if 1 <= idx <= len(ebay_items)
    ]
    
    removed_count = len(ebay_items) - len(filtered_items)
    if removed_count > 0:
        logger.debug(f"Dropped {removed_count} non-matches ({len(filtered_items)} kept)")
    else:
        logger.debug("All listings matched")

    if removed_count > 0 and reasons:
        logger.debug("Why items were dropped (first 3):")
        rejected_reasons = [(idx, r) for idx, r in reasons.items() if int(idx) not in comparable_indices]
        for idx, reason in rejected_reasons[:3]:
            logger.debug(f"   {idx}: {reason}")
    
    return (comparable_indices, filtered_items, reasons)


def filter_ebay_results_with_openai(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[dict], dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.

    Chunks eBay items into batches and makes parallel async OpenAI calls (one per batch)
    to analyze each item's title, description, and condition against the FB listing. Removes
    items that are accessories, different models, or otherwise not comparable. This improves
    price comparison accuracy by ensuring only truly similar items are used for the market average.
    
    Returns tuple of (comparable_indices, filtered list of eBay items, reasons dict) or None if filtering fails.
    comparable_indices is a list of 1-based indices of items that passed filtering.
    The reasons dict maps 1-based item indices to short reason strings explaining accept/reject decisions.
    Format: [1, 3, 5], [{title, price, url}, ...], {"1": "reason", "2": "reason", ...}
    """
    if not AsyncOpenAI:
        logger.debug("Search suggestions unavailable — skipping match filter")
        return None
    if not OPENAI_API_KEY:
        logger.debug("Search suggestions not configured — skipping match filter")
        return None
    
    if not ebay_items:
        return ([], ebay_items, {})
    
    try:
        # Run the async filtering. Use a worker thread if we're in an async context
        # (asyncio.run cannot be called when a loop is already running).
        try:
            asyncio.get_running_loop()
            has_loop = True
        except RuntimeError:
            has_loop = False

        if has_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    lambda: asyncio.run(_filter_ebay_results_async(listing, ebay_items, cancelled))
                )
                result = future.result()
        else:
            result = asyncio.run(_filter_ebay_results_async(listing, ebay_items, cancelled))

        return result
    except SearchCancelledError:
        raise
    except Exception as e:
        logger.warning(f"Match check failed: {e} — using all listings")
        return None
