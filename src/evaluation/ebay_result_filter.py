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
from src.utils.search_runtime_config import (
    POST_FILTER_BATCH_SIZE,
    POST_FILTER_MAX_CONCURRENT_BATCHES,
    POST_FILTER_BATCH_START_DELAY_SEC,
    POST_FILTER_CANCEL_POLL_INTERVAL_SEC,
)

logger = setup_colored_logger("ebay_result_filter")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BATCH_FILTER_MAX_OUTPUT_TOKENS = 3000
LISTING_TITLE_LOG_PREVIEW_LEN = 60


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
) -> List[Tuple[int, str, str, float]]:
    """
    Filter a batch of eBay items against a FB listing using OpenAI.

    start_index: 1-based global index of the first item in this batch.
    Returns list of (1-based global index, decision, reason, ratio) for each item.
    Decision is one of: "accept", "reject", "maybe".
    Ratio is a positive number for quantity normalization (defaults to 1.0).
    On API error or invalid response, keeps all items in the batch (fail-open with "accept").
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
            return [(start_index + i, "accept", "", 1.0) for i in range(len(items))]
        results_list = _try_parse_results_list(raw_content, len(items))
        if results_list is None:
            logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: invalid JSON — keeping all")
            return [(start_index + i, "accept", "", 1.0) for i in range(len(items))]
        out = []
        for i, r in enumerate(results_list):
            if not isinstance(r, dict):
                out.append((start_index + i, "accept", "", 1.0))
                continue
            decision = r.get("decision", "accept")
            if decision not in ("accept", "reject", "maybe"):
                decision = "accept"
            reason = r.get("reason", "")
            if not isinstance(reason, str):
                reason = str(reason)
            ratio = r.get("ratio", 1.0)
            if not isinstance(ratio, (int, float)) or ratio <= 0:
                ratio = 1.0
            out.append((start_index + i, decision, reason, float(ratio)))
        return out
    except Exception as e:
        logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: API error ({e}) — keeping all")
        return [(start_index + i, "accept", "", 1.0) for i in range(len(items))]


async def _filter_ebay_results_async(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """
    Async implementation of eBay result filtering using batched API calls.

    Chunks items into batches of 5 and runs async OpenAI calls with bounded
    concurrency. Batch starts are staggered by a small delay to reduce
    rate-limit pressure. Cancellation is checked while launching and while
    waiting for batch completion.
    
    Returns tuple of (accept_indices, maybe_indices, filtered_items, decisions) where:
    - accept_indices: 1-based indices of items marked "accept"
    - maybe_indices: 1-based indices of items marked "maybe"
    - filtered_items: list of items that passed filtering (accept + maybe)
    - decisions: dict mapping 1-based index to {decision, reason, ratio}
    """
    if not AsyncOpenAI:
        logger.debug("Async OpenAI unavailable — skipping match filter")
        return None
    if not OPENAI_API_KEY:
        logger.debug("Search suggestions not configured — skipping match filter")
        return None

    if not ebay_items:
        return ([], [], ebay_items, {})

    if cancelled and cancelled.is_set():
        raise SearchCancelledError("Search was cancelled by user")

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)

    async def _cancel_running_tasks(tasks: set[asyncio.Task]) -> None:
        """Cancel running batch tasks and wait for them to finish cleanup."""
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()

    try:
        batches = []
        for i in range(0, len(ebay_items), POST_FILTER_BATCH_SIZE):
            batch = ebay_items[i : i + POST_FILTER_BATCH_SIZE]
            start_index = i + 1
            batches.append((batch, start_index))

        running_tasks: set[asyncio.Task] = set()
        results: List[Tuple[int, str, str, float]] = []
        next_batch_idx = 0

        while next_batch_idx < len(batches) or running_tasks:
            if cancelled and cancelled.is_set():
                await _cancel_running_tasks(running_tasks)
                raise SearchCancelledError("Search was cancelled by user")

            can_launch_more = (
                next_batch_idx < len(batches)
                and len(running_tasks) < POST_FILTER_MAX_CONCURRENT_BATCHES
            )
            if can_launch_more:
                batch, start_index = batches[next_batch_idx]
                if cancelled and cancelled.is_set():
                    await _cancel_running_tasks(running_tasks)
                    raise SearchCancelledError("Search was cancelled by user")
                task = asyncio.create_task(
                    _filter_batch(client, fb_listing_text, batch, start_index)
                )
                running_tasks.add(task)
                next_batch_idx += 1

                if POST_FILTER_BATCH_START_DELAY_SEC > 0 and next_batch_idx < len(batches):
                    done, _ = await asyncio.wait(
                        running_tasks,
                        timeout=POST_FILTER_BATCH_START_DELAY_SEC,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for finished_task in done:
                        running_tasks.remove(finished_task)
                        try:
                            results.extend(finished_task.result())
                        except asyncio.CancelledError:
                            await _cancel_running_tasks(running_tasks)
                            raise SearchCancelledError("Search was cancelled by user")
                continue

            if running_tasks:
                done, _ = await asyncio.wait(
                    running_tasks,
                    timeout=POST_FILTER_CANCEL_POLL_INTERVAL_SEC,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for finished_task in done:
                    running_tasks.remove(finished_task)
                    try:
                        results.extend(finished_task.result())
                    except asyncio.CancelledError:
                        await _cancel_running_tasks(running_tasks)
                        raise SearchCancelledError("Search was cancelled by user")
    finally:
        # Ensure client is closed before event loop closes
        try:
            await client.close()
        except Exception:
            pass

    # Aggregate results by decision type
    accept_indices = []
    maybe_indices = []
    decisions = {}

    for item_index, decision, reason, ratio in results:
        decisions[str(item_index)] = {"decision": decision, "reason": reason, "ratio": ratio}
        if decision == "accept":
            accept_indices.append(item_index)
        elif decision == "maybe":
            maybe_indices.append(item_index)
        # "reject" items are not added to any list

    # Sort indices to maintain order
    accept_indices.sort()
    maybe_indices.sort()

    # Combine accept + maybe for filtered items (indices are 1-based, convert to 0-based)
    all_kept_indices = sorted(accept_indices + maybe_indices)
    filtered_items = [
        ebay_items[idx - 1]
        for idx in all_kept_indices
        if 1 <= idx <= len(ebay_items)
    ]

    listing_title_preview = (listing.title or "").strip()
    if len(listing_title_preview) > LISTING_TITLE_LOG_PREVIEW_LEN:
        listing_title_preview = listing_title_preview[:LISTING_TITLE_LOG_PREVIEW_LEN] + ".."
    listing_prefix = f"[{listing_title_preview}] " if listing_title_preview else ""

    reject_count = len(ebay_items) - len(filtered_items)
    if reject_count > 0 or maybe_indices:
        logger.debug(
            f"{listing_prefix}Filter results: {len(accept_indices)} accept, "
            f"{len(maybe_indices)} maybe, {reject_count} reject"
        )
    else:
        logger.debug(f"{listing_prefix}All listings accepted")

    return (accept_indices, maybe_indices, filtered_items, decisions)


def filter_ebay_results_with_openai(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.

    Chunks eBay items into batches of 5 and makes bounded concurrent async OpenAI calls to
    analyze each item's title, description, and condition against the FB listing. Batch starts
    are slightly staggered to reduce rate-limit pressure. Categorizes items as accept, maybe,
    or reject. This improves price comparison accuracy by ensuring only truly similar items are
    used for the market average, with "maybe" items receiving partial weight.
    
    Returns tuple of (accept_indices, maybe_indices, filtered_items, decisions) or None if filtering fails.
    - accept_indices: 1-based indices of items marked "accept" (full weight in average)
    - maybe_indices: 1-based indices of items marked "maybe" (0.5 weight in average)
    - filtered_items: list of items that passed filtering (accept + maybe)
    - decisions: dict mapping 1-based index to {decision, reason, ratio}
    """
    if not AsyncOpenAI:
        logger.debug("Search suggestions unavailable — skipping match filter")
        return None
    if not OPENAI_API_KEY:
        logger.debug("Search suggestions not configured — skipping match filter")
        return None

    if not ebay_items:
        return ([], [], ebay_items, {})

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
