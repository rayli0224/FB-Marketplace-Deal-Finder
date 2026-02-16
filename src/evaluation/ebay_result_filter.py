"""
eBay result filtering for price comparison accuracy.

Uses OpenAI to filter eBay search results, keeping only items truly comparable
to a Facebook Marketplace listing. Removes accessories, different models, and
other non-comparable items so the market average reflects similar products only.
"""

import asyncio
import json
import os
import threading
from typing import List, Optional, Tuple

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing, SearchCancelledError
from src.utils.colored_logger import setup_colored_logger, log_warning
from src.evaluation.prompts import (
    RESULT_FILTERING_SYSTEM_MESSAGE,
    format_fb_listing_for_prompt,
    get_batch_filtering_prompt,
)
from src.evaluation.openai_client import (
    create_async_response,
    extract_response_output_text,
    strip_markdown_code_fences,
)

logger = setup_colored_logger("ebay_result_filter")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BATCH_FILTER_MAX_OUTPUT_TOKENS = 3000
POST_FILTER_BATCH_SIZE = 5


def _format_ebay_batch(items: List[dict]) -> str:
    """
    Format a batch of eBay items as text for the batch filtering prompt.
    Items are numbered 1-based within the batch.
    """
    parts = []
    for i, item in enumerate(items):
        title = item.get("title", "")
        price = item.get("price", 0)
        description = item.get("description", "")
        condition = item.get("condition", "")
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
    content = strip_markdown_code_fences(raw_content)
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
        response = await create_async_response(
            client,
            instructions=RESULT_FILTERING_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=BATCH_FILTER_MAX_OUTPUT_TOKENS,
        )
        raw_content = extract_response_output_text(response)
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

    Chunks items into batches of 5 and runs one async OpenAI call per batch.
    Runs batches sequentially so cancellation can be checked between each.
    Aggregates results into the same format as the original single-call version.
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
    fb_listing_text = format_fb_listing_for_prompt(listing)

    batches = []
    for i in range(0, len(ebay_items), POST_FILTER_BATCH_SIZE):
        batch = ebay_items[i : i + POST_FILTER_BATCH_SIZE]
        start_index = i + 1
        batches.append((batch, start_index))

    results = []
    for batch, start_index in batches:
        if cancelled and cancelled.is_set():
            raise SearchCancelledError("Search was cancelled by user")
        batch_result = await _filter_batch(client, fb_listing_text, batch, start_index)
        results.extend(batch_result)

    comparable_indices = []
    reasons = {}

    for item_index, rejected, reason in results:
        reasons[str(item_index)] = reason
        if not rejected:
            comparable_indices.append(item_index)

    comparable_indices.sort()

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

    Chunks eBay items into batches of 5 and makes parallel async OpenAI calls (one per batch)
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
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _filter_ebay_results_async(listing, ebay_items, cancelled),
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(_filter_ebay_results_async(listing, ebay_items, cancelled))
    except SearchCancelledError:
        raise
    except Exception as e:
        log_warning(logger, f"Match check failed: {e} — using all listings")
        return None
