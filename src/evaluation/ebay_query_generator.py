"""
eBay search query generation from Facebook Marketplace listings.

Uses OpenAI to generate optimized eBay search queries for comparing FB listings
to sold eBay prices. Includes pre-filtering to reject listings that lack enough
detail for a useful comparison.
"""

import os
from typing import Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_error_short, log_warning, truncate_lines
from src.evaluation.prompts import (
    QUERY_GENERATION_SYSTEM_MESSAGE,
    PRE_FILTERING_SYSTEM_MESSAGE,
    format_fb_listing_for_prompt,
    get_pre_filtering_prompt,
    get_query_generation_prompt,
)
from src.evaluation.openai_client import (
    create_sync_response,
    extract_response_output_text,
    try_parse_json_dict,
)

logger = setup_colored_logger("ebay_query_generator")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000
PRE_FILTER_MAX_OUTPUT_TOKENS = 500


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str,
) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """
    Generate an optimized eBay search query for a FB listing.
    Returns (enhanced_query, skip_reason) or None on generic failure.
    On success: (query, None). On model rejection: (None, reason). On other failure: None.
    """
    if not OpenAI:
        logger.error("❌ Search suggestions unavailable (required package not installed).")
        return None
    if not OPENAI_API_KEY:
        log_warning(logger, "Search suggestions not available (missing configuration).")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)

    pre_filtering_prompt = get_pre_filtering_prompt(fb_listing_text)
    try:
        pre_filtering_response = create_sync_response(
            client,
            instructions=PRE_FILTERING_SYSTEM_MESSAGE,
            prompt=pre_filtering_prompt,
            max_output_tokens=PRE_FILTER_MAX_OUTPUT_TOKENS,
        )
        pre_raw = extract_response_output_text(pre_filtering_response)
        pre_result = try_parse_json_dict(pre_raw)
        if pre_result is None:
            logger.debug(f"Pre-filter response was not valid JSON: {pre_raw[:200] if pre_raw else '(empty)'}")
        elif pre_result.get("rejected"):
            logger.debug(f"Pre-filter rejected: {pre_result.get('reason', 'insufficient information')}")
            return (None, pre_result.get("reason", "insufficient information"))
        else:
            logger.debug(f"Pre-filter accepted: {pre_result.get('reason', '')}")
    except Exception as e:
        logger.warning(f"Pre-filter API call failed: {e}")
        pre_result = None

    prompt = get_query_generation_prompt(fb_listing_text)

    try:
        response = create_sync_response(
            client,
            instructions=QUERY_GENERATION_SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=QUERY_GENERATION_MAX_OUTPUT_TOKENS,
        )
        raw_content = extract_response_output_text(response)
        try:
            truncated_content = truncate_lines(raw_content, 5)
            logger.debug(f"eBay search suggestion (preview):\n\t{truncated_content}")
        except Exception as e:
            logger.debug(f"Could not show preview: {e}")

        result = try_parse_json_dict(raw_content)
        if result is None:
            log_error_short(logger, "Search suggestion response was invalid JSON")
            logger.debug(f"Response content: {raw_content}")
            return None

        enhanced_query = result.get("enhanced_query", original_query)
        logger.debug(f"Search: '{enhanced_query}'")
        return (enhanced_query, None)
    except Exception as e:
        log_error_short(logger, f"Search suggestion request failed: {e}")
        return None
