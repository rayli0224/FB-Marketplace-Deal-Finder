"""
OpenAI API helper functions for query generation and result filtering.

Provides helper functions for making OpenAI API calls to generate optimized eBay
search queries and filter eBay results to match Facebook Marketplace listings.
"""

import os
import json
import asyncio
from typing import Optional, Tuple, List, Any

try:
    from openai import OpenAI, AsyncOpenAI
except ImportError:
    OpenAI = None
    AsyncOpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_error_short, truncate_lines
from src.utils.prompts import (
    QUERY_GENERATION_SYSTEM_MESSAGE,
    RESULT_FILTERING_SYSTEM_MESSAGE,
    get_query_generation_prompt,
    get_pre_filtering_prompt,
    get_single_item_filtering_prompt,
)

logger = setup_colored_logger("openai_helpers")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-5-mini"
PRE_FILTER_MAX_OUTPUT_TOKENS = 150
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000
SINGLE_ITEM_FILTER_MAX_OUTPUT_TOKENS = 1000


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


def _create_sync_response(
    client: "OpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
) -> Any:
    """
    Create a sync OpenAI Responses API request with shared defaults.
    """
    return client.responses.create(
        model=OPENAI_MODEL,
        instructions=instructions,
        input=prompt,
        max_output_tokens=max_output_tokens,
    )


async def _create_async_response(
    client: "AsyncOpenAI",
    *,
    instructions: Optional[str],
    prompt: str,
    max_output_tokens: int,
) -> Any:
    """
    Create an async OpenAI Responses API request with shared defaults.
    """
    return await client.responses.create(
        model=OPENAI_MODEL,
        instructions=instructions,
        input=prompt,
        max_output_tokens=max_output_tokens,
    )


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
        instructions=None,
        prompt=pre_filtering_prompt,
        max_output_tokens=PRE_FILTER_MAX_OUTPUT_TOKENS,
    )
    pre_raw = _extract_response_output_text(pre_filtering_response)
    pre_result = _try_parse_json_dict(pre_raw)
    if isinstance(pre_result, dict) and pre_result.get("rejected"):
        logger.debug(f"Pre-filter for FB listing rejected:\n\t{pre_result.get('reason', 'insufficient information')}")
        return None, None, pre_result.get("reason", "insufficient information")
    if isinstance(pre_result, dict):
        logger.debug(f"Pre-filter for FB listing accepted:\n\t{pre_result.get('reason', '')}")
    
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


def _format_single_ebay_listing(listing: dict) -> str:
    """
    Format a single eBay listing as text for the filtering prompt.
    Includes title, price, condition, and truncated description.
    """
    title = listing.get('title', '')
    price = listing.get('price', 0)
    description = listing.get('description', '')
    condition = listing.get('condition', '')
    
    listing_text = f"eBay listing:\n- Title: {title}\n- Price: ${price:.2f}"
    if condition:
        listing_text += f"\n- Condition: {condition}"
    if description:
        listing_text += f"\n- Description: {description}"
    
    return listing_text


async def _filter_single_item(
    client: "AsyncOpenAI",
    fb_listing_text: str,
    item: dict,
    item_index: int,
) -> Tuple[int, bool, str]:
    """
    Filter a single eBay item against a FB listing using OpenAI.
    
    Makes an async API call to determine if the eBay item is comparable to the FB listing.
    Returns a tuple of (1-based item index, rejected boolean, reason string).
    On API error, returns (index, False, "") to keep the item (fail-open).
    """
    ebay_item_text = _format_single_ebay_listing(item)
    prompt = get_single_item_filtering_prompt(
        fb_listing_text=fb_listing_text,
        ebay_item_text=ebay_item_text,
    )

    try:
        response = await _create_async_response(
            client,
            instructions=RESULT_FILTERING_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=SINGLE_ITEM_FILTER_MAX_OUTPUT_TOKENS,
        )

        raw_content = _extract_response_output_text(response)
        if not raw_content:
            logger.debug(f"Item {item_index}: empty response — keeping item")
            return (item_index, False, "")

        result = _try_parse_json_dict(raw_content)
        if result is None:
            preview = raw_content[:200] or "empty"
            logger.debug(f"Item {item_index}: invalid JSON ({preview}) — keeping item")
            return (item_index, False, "")

        rejected = bool(result.get("rejected", False))
        reason = result.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)
        return (item_index, rejected, reason)

    except Exception as e:
        logger.debug(f"Item {item_index}: API error ({type(e).__name__}: {e}) — keeping item")
        return (item_index, False, "")



async def _filter_ebay_results_async(
    listing: Listing,
    ebay_items: List[dict]
) -> Optional[Tuple[List[int], List[dict], dict]]:
    """
    Async implementation of eBay result filtering using parallel API calls.
    
    Creates one async OpenAI call per eBay item and runs them all concurrently.
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
    
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = _format_fb_listing(listing)
    
    # Create tasks for all items (1-based indices)
    tasks = [
        _filter_single_item(
            client=client,
            fb_listing_text=fb_listing_text,
            item=item,
            item_index=i + 1,
        )
        for i, item in enumerate(ebay_items)
    ]
    
    # Run all filtering tasks in parallel
    results = await asyncio.gather(*tasks)
    
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
    ebay_items: List[dict]
) -> Optional[Tuple[List[int], List[dict], dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.
    
    Makes parallel async OpenAI calls (one per eBay item) to analyze each item's title,
    description, and condition and compare them to the FB listing. Removes items that are
    accessories, different models, or otherwise not comparable. This improves price comparison
    accuracy by ensuring only truly similar items are used for calculating the market average.
    
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
                    _filter_ebay_results_async(listing, ebay_items)
                )
                return future.result()
        except RuntimeError:
            # No running event loop, we can use asyncio.run directly
            return asyncio.run(_filter_ebay_results_async(listing, ebay_items))
    except Exception as e:
        logger.warning(f"Match check failed: {e} — using all listings")
        return None
