"""
eBay results filter — filters eBay search results for price comparison accuracy.

Uses OpenAI to filter eBay results, keeping only items truly comparable to a
Facebook Marketplace listing.
"""

import asyncio
import concurrent.futures
import json
import os
import threading
from typing import List, Optional, Tuple

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing, SearchCancelledError
from src.scrapers.ebay_scraper_v2 import PriceStats
from src.utils.colored_logger import setup_colored_logger, log_warning
from src.evaluation.ebay_results_filter.prompts import SYSTEM_MESSAGE, get_batch_filtering_prompt
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

logger = setup_colored_logger("ebay_results_filter")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
BATCH_FILTER_MAX_OUTPUT_TOKENS = 3000
LISTING_TITLE_LOG_PREVIEW_LEN = 60


def _format_ebay_batch(items: List[dict]) -> str:
    """Format a batch of eBay items as text for the batch filtering prompt."""
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
    """Parse batch filter response. Returns None if invalid."""
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
    product_recon_json: str,
    items: List[dict],
    start_index: int,
    cancelled: Optional[threading.Event] = None,
) -> List[Tuple[int, str, str]]:
    """Filter a batch of eBay items against a FB listing using OpenAI."""
    if not items:
        return []
    ebay_items_text = _format_ebay_batch(items)
    prompt = get_batch_filtering_prompt(
        product_recon_json=product_recon_json,
        ebay_items_text=ebay_items_text,
    )
    try:
        response = await create_async_response(
            client,
            instructions=SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=BATCH_FILTER_MAX_OUTPUT_TOKENS,
            cancelled=cancelled,
        )
        raw_content = extract_response_output_text(response)
        if not raw_content:
            logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: empty response — keeping all")
            return [(start_index + i, "accept", "") for i in range(len(items))]
        results_list = _try_parse_results_list(raw_content, len(items))
        if results_list is None:
            logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: invalid JSON — keeping all")
            return [(start_index + i, "accept", "") for i in range(len(items))]
        out = []
        for i, r in enumerate(results_list):
            if not isinstance(r, dict):
                out.append((start_index + i, "accept", ""))
                continue
            decision = r.get("decision", "accept")
            if decision not in ("accept", "reject", "maybe"):
                decision = "accept"
            reason = r.get("reason", "")
            if not isinstance(reason, str):
                reason = str(reason)
            out.append((start_index + i, decision, reason))
        return out
    except SearchCancelledError:
        # Propagate cancellation immediately
        raise
    except Exception as e:
        logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: API error ({e}) — keeping all")
        return [(start_index + i, "accept", "") for i in range(len(items))]


async def _filter_ebay_results_async(
    listing: Listing,
    ebay_items: List[dict],
    product_recon_json: str,
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """Async implementation of eBay result filtering using batched API calls."""
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

    async def _cancel_running_tasks(tasks: set[asyncio.Task]) -> None:
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()

    async def _collect_batch_results(
        done: set[asyncio.Task],
        running_tasks: set[asyncio.Task],
        results_list: List[Tuple[int, str, str]],
    ) -> None:
        for finished_task in done:
            running_tasks.discard(finished_task)
            try:
                results_list.extend(finished_task.result())
            except asyncio.CancelledError:
                # Task was canceled - cancel all remaining tasks and propagate
                await _cancel_running_tasks(running_tasks)
                raise SearchCancelledError("Search was cancelled by user")
            except SearchCancelledError:
                # Already a SearchCancelledError - cancel remaining tasks and propagate
                await _cancel_running_tasks(running_tasks)
                raise

    try:
        batches = []
        for i in range(0, len(ebay_items), POST_FILTER_BATCH_SIZE):
            batch = ebay_items[i : i + POST_FILTER_BATCH_SIZE]
            start_index = i + 1
            batches.append((batch, start_index))

        running_tasks: set[asyncio.Task] = set()
        results: List[Tuple[int, str, str]] = []
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
                    _filter_batch(client, product_recon_json, batch, start_index, cancelled=cancelled)
                )
                running_tasks.add(task)
                next_batch_idx += 1

                if POST_FILTER_BATCH_START_DELAY_SEC > 0 and next_batch_idx < len(batches):
                    # Check cancellation before waiting
                    if cancelled and cancelled.is_set():
                        await _cancel_running_tasks(running_tasks)
                        raise SearchCancelledError("Search was cancelled by user")
                    
                    done, _ = await asyncio.wait(
                        running_tasks,
                        timeout=POST_FILTER_BATCH_START_DELAY_SEC,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    
                    if cancelled and cancelled.is_set():
                        await _cancel_running_tasks(running_tasks)
                        raise SearchCancelledError("Search was cancelled by user")
                    
                    await _collect_batch_results(done, running_tasks, results)
                continue

            if running_tasks:
                # Check cancellation before waiting
                if cancelled and cancelled.is_set():
                    await _cancel_running_tasks(running_tasks)
                    raise SearchCancelledError("Search was cancelled by user")
                
                done, _ = await asyncio.wait(
                    running_tasks,
                    timeout=POST_FILTER_CANCEL_POLL_INTERVAL_SEC,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                
                if cancelled and cancelled.is_set():
                    await _cancel_running_tasks(running_tasks)
                    raise SearchCancelledError("Search was cancelled by user")
                
                await _collect_batch_results(done, running_tasks, results)
    finally:
        try:
            await client.close()
        except Exception:
            pass

    accept_indices = []
    maybe_indices = []
    decisions = {}

    for item_index, decision, reason in results:
        decisions[str(item_index)] = {"decision": decision, "reason": reason}
        if decision == "accept":
            accept_indices.append(item_index)
        elif decision == "maybe":
            maybe_indices.append(item_index)

    accept_indices.sort()
    maybe_indices.sort()

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
    product_recon_json: str,
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """Filter eBay search results to keep only items comparable to the FB listing."""
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
            asyncio.get_running_loop()
            # We're already in an async context, so run in a thread pool
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _filter_ebay_results_async(listing, ebay_items, product_recon_json, cancelled),
                )
                # Poll future.result() with timeout to check cancellation periodically
                while True:
                    if cancelled and cancelled.is_set():
                        future.cancel()
                        raise SearchCancelledError("Search was cancelled by user")
                    try:
                        return future.result(timeout=0.1)
                    except concurrent.futures.TimeoutError:
                        # Continue polling
                        continue
        except RuntimeError:
            # No running event loop, can use asyncio.run directly
            return asyncio.run(_filter_ebay_results_async(listing, ebay_items, product_recon_json, cancelled))
    except SearchCancelledError:
        raise
    except Exception as e:
        log_warning(logger, f"Match check failed: {e} — using all listings")
        return None


def _clone_price_stats(stats: PriceStats) -> PriceStats:
    """Clone eBay price stats so filtering can mutate safely."""
    cloned_items = None
    if stats.item_summaries is not None:
        cloned_items = [{**item} for item in stats.item_summaries]
    return PriceStats(
        search_term=stats.search_term,
        sample_size=stats.sample_size,
        average=stats.average,
        raw_prices=list(stats.raw_prices),
        item_summaries=cloned_items,
    )


def filter_ebay_results_for_listing(
    listing: Listing,
    ebay_stats: PriceStats,
    product_recon_json: str,
    cancelled: Optional[threading.Event] = None,
) -> Tuple[PriceStats, Optional[str]]:
    """
    Filter eBay search results against a FB listing and compute weighted average.

    Returns (filtered_stats, no_comp_reason). no_comp_reason is "no_comparable"
    when no items matched; otherwise None.
    """
    stats = _clone_price_stats(ebay_stats)
    ebay_items = getattr(stats, "item_summaries", None)
    if not ebay_items:
        return (stats, None)

    filter_result = filter_ebay_results_with_openai(
        listing,
        ebay_items,
        product_recon_json=product_recon_json,
        cancelled=cancelled,
    )
    if filter_result is not None and asyncio.iscoroutine(filter_result):
        log_warning(logger, "Filter returned coroutine instead of result — using all listings")
        filter_result = None

    if filter_result is None:
        logger.debug("Filtering unavailable (OpenAI not configured) - using original results")
        stats.item_summaries = [
            {**item, "filtered": False, "filterStatus": "accept"}
            for item in ebay_items
        ]
        return (stats, None)

    accept_indices, maybe_indices, filtered_items, decisions = filter_result
    accept_indices_set = set(accept_indices)
    maybe_indices_set = set(maybe_indices)
    all_items_with_filter_flag = []
    for i, item in enumerate(ebay_items):
        item_idx = i + 1
        decision_info = decisions.get(str(item_idx), {})
        decision = decision_info.get("decision", "accept")
        reason = decision_info.get("reason", "")
        is_rejected = decision == "reject"
        item_with_flags = {
            **item,
            "filtered": is_rejected,
            "filterStatus": decision,
        }
        if reason:
            item_with_flags["filterReason"] = reason
        all_items_with_filter_flag.append(item_with_flags)

    weighted_sum = 0.0
    total_weight = 0.0
    for i, item in enumerate(ebay_items):
        item_idx = i + 1
        if item_idx in accept_indices_set:
            weighted_sum += item["price"] * 1.0
            total_weight += 1.0
        elif item_idx in maybe_indices_set:
            weighted_sum += item["price"] * 0.5
            total_weight += 0.5

    if len(filtered_items) != len(ebay_items) or maybe_indices:
        filtered_prices = [item["price"] for item in filtered_items]
        stats.raw_prices = sorted(filtered_prices)
        stats.item_summaries = all_items_with_filter_flag

        if total_weight >= 3.0:
            stats.average = weighted_sum / total_weight
            stats.sample_size = len(filtered_items)
            logger.info(f"📋 {len(accept_indices)} accept + {len(maybe_indices)} maybe (weighted avg ${stats.average:.2f})")
        elif total_weight > 0:
            stats.average = weighted_sum / total_weight
            stats.sample_size = len(filtered_items)
            log_warning(logger, f"Only {len(accept_indices)} accept + {len(maybe_indices)} maybe (need more to compare reliably)")
        else:
            log_warning(logger, "No matching listings — can't compare price")
            stats.average = 0
            stats.sample_size = 0
            stats.raw_prices = []
            return (stats, "no_comparable")
    else:
        logger.debug("All items deemed comparable")
        stats.item_summaries = all_items_with_filter_flag

    return (stats, None)
