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
    PRE_FILTERING_SYSTEM_MESSAGE,
    QUERY_GENERATION_SYSTEM_MESSAGE,
    RESULT_FILTERING_SYSTEM_MESSAGE,
    get_query_generation_prompt,
    get_pre_filtering_prompt,
    get_batch_filtering_prompt,
)

logger = setup_colored_logger("openai_helpers")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-5-mini"
PRE_FILTER_MAX_OUTPUT_TOKENS = 500
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000
BATCH_FILTER_MAX_OUTPUT_TOKENS = 3000
POST_FILTER_BATCH_SIZE = 5
RATE_LIMIT_RETRY_DELAY_SEC = 0.5
RATE_LIMIT_MAX_RETRIES = 3


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

    Uses the convenience output_text property when available, then falls back to
    manually traversing the structured output blocks.
    """
    # Try the convenience property first
    if hasattr(response, "output_text"):
        try:
            output_text = response.output_text
            logger.debug(f"output_text property returned: {repr(output_text[:100]) if output_text else '(empty)'}")
            if output_text and output_text.strip():
                return output_text.strip()
        except Exception as e:
            logger.debug(f"Error accessing output_text property: {e}")
    
    # Fallback: manually traverse the output structure
    output_blocks = getattr(response, "output", None) or []
    logger.debug(f"output blocks: {len(output_blocks) if output_blocks else 0}")
    
    texts = []
    for idx, output_item in enumerate(output_blocks):
        logger.debug(f"Output item {idx}: type={getattr(output_item, 'type', 'unknown')}, class={type(output_item).__name__}")
        
        # Check if this is a message output item
        item_type = getattr(output_item, "type", None)
        if item_type == "message":
            # Get the content list
            content_list = getattr(output_item, "content", None) or []
            logger.debug(f"  Message has {len(content_list)} content items")
            for content_idx, content_item in enumerate(content_list):
                content_type = getattr(content_item, "type", None)
                logger.debug(f"    Content {content_idx}: type={content_type}")
                # Check if this is a text content item
                if content_type == "output_text":
                    text = getattr(content_item, "text", None)
                    logger.debug(f"      Found text: {repr(text[:50]) if text else '(none)'}")
                    if text:
                        texts.append(text)
        else:
            # Try to get text directly if it's not a message
            if hasattr(output_item, "text"):
                text = getattr(output_item, "text", None)
                logger.debug(f"  Non-message item has text attribute: {repr(text[:50]) if text else '(none)'}")
                if text:
                    texts.append(text)
    
    result = "".join(texts).strip() if texts else ""
    logger.debug(f"Final extracted text length: {len(result)}")
    return result


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
    
    # Verify the responses API is available
    if not hasattr(client, 'responses'):
        logger.error("OpenAI client does not have 'responses' attribute - API may not be available")
        return None
    
    fb_listing_text = _format_fb_listing(listing)
    
    pre_filtering_prompt = get_pre_filtering_prompt(fb_listing_text)
    try:
        logger.debug("Calling pre-filter API...")
        pre_filtering_response = _create_sync_response(
            client,
            instructions=PRE_FILTERING_SYSTEM_MESSAGE,
            prompt=pre_filtering_prompt,
            max_output_tokens=PRE_FILTER_MAX_OUTPUT_TOKENS,
        )
        logger.debug("Pre-filter API call completed")
        pre_raw = _extract_response_output_text(pre_filtering_response)
        logger.debug(f"Pre-filter extracted text length: {len(pre_raw) if pre_raw else 0}")
        if pre_raw:
            logger.debug(f"Pre-filter content: {pre_raw}")
        pre_result = _try_parse_json_dict(pre_raw)
    except Exception as e:
        logger.warning(f"Pre-filter API call failed: {e}")
        pre_result = None
        pre_raw = ""
    if pre_result is None:
        logger.debug(f"Pre-filter response was not valid JSON: {pre_raw[:200] if pre_raw else '(empty)'}")
    elif pre_result.get("rejected"):
        logger.info(f"Pre-filter rejected: {pre_result.get('reason', 'insufficient information')}")
        return None, None, pre_result.get("reason", "insufficient information")
    else:
        logger.info(f"Pre-filter accepted: {pre_result.get('reason', '')}")
    
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
) -> List[Tuple[int, str, str]]:
    """
    Filter a batch of eBay items against a FB listing using OpenAI.

    start_index: 1-based global index of the first item in this batch.
    Returns list of (1-based global index, decision, reason) for each item.
    Decision is one of: "accept", "reject", "maybe".
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
        response = await _create_async_response(
            client,
            instructions=RESULT_FILTERING_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=BATCH_FILTER_MAX_OUTPUT_TOKENS,
        )
        raw_content = _extract_response_output_text(response)
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
    except Exception as e:
        logger.debug(f"Batch {start_index}-{start_index + len(items) - 1}: API error ({e}) — keeping all")
        return [(start_index + i, "accept", "") for i in range(len(items))]



async def _filter_ebay_results_async(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """
    Async implementation of eBay result filtering using batched API calls.

    Chunks items into batches of 5 and runs one async OpenAI call per batch.
    Runs batches sequentially so cancellation can be checked between each.
    
    Returns tuple of (accept_indices, maybe_indices, filtered_items, decisions) where:
    - accept_indices: 1-based indices of items marked "accept"
    - maybe_indices: 1-based indices of items marked "maybe"
    - filtered_items: list of items that passed filtering (accept + maybe)
    - decisions: dict mapping 1-based index to {decision, reason}
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
    fb_listing_text = _format_fb_listing(listing)

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
    
    # Aggregate results by decision type
    accept_indices = []
    maybe_indices = []
    decisions = {}
    
    for item_index, decision, reason in results:
        decisions[str(item_index)] = {"decision": decision, "reason": reason}
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
    
    reject_count = len(ebay_items) - len(filtered_items)
    if reject_count > 0 or maybe_indices:
        logger.debug(f"Filter results: {len(accept_indices)} accept, {len(maybe_indices)} maybe, {reject_count} reject")
    else:
        logger.debug("All listings accepted")

    if reject_count > 0 and decisions:
        logger.debug("Why items were rejected (first 3):")
        rejected = [(idx, d) for idx, d in decisions.items() if d["decision"] == "reject"]
        for idx, d in rejected[:3]:
            logger.debug(f"   {idx}: {d['reason']}")
    
    return (accept_indices, maybe_indices, filtered_items, decisions)


def filter_ebay_results_with_openai(
    listing: Listing,
    ebay_items: List[dict],
    cancelled: Optional[threading.Event] = None,
) -> Optional[Tuple[List[int], List[int], List[dict], dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.

    Chunks eBay items into batches of 5 and makes parallel async OpenAI calls (one per batch)
    to analyze each item's title, description, and condition against the FB listing. Categorizes
    items as accept, maybe, or reject. This improves price comparison accuracy by ensuring only
    truly similar items are used for the market average, with "maybe" items receiving partial weight.
    
    Returns tuple of (accept_indices, maybe_indices, filtered_items, decisions) or None if filtering fails.
    - accept_indices: 1-based indices of items marked "accept" (full weight in average)
    - maybe_indices: 1-based indices of items marked "maybe" (0.5 weight in average)
    - filtered_items: list of items that passed filtering (accept + maybe)
    - decisions: dict mapping 1-based index to {decision, reason}
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
        # Run the async filtering in a new event loop
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, use nest_asyncio pattern or run in executor
            # For simplicity, create a new thread with its own event loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _filter_ebay_results_async(listing, ebay_items, cancelled),
                )
                return future.result()
        except RuntimeError:
            # No running event loop, we can use asyncio.run directly
            return asyncio.run(_filter_ebay_results_async(listing, ebay_items, cancelled))
    except SearchCancelledError:
        raise
    except Exception as e:
        logger.warning(f"Match check failed: {e} — using all listings")
        return None
