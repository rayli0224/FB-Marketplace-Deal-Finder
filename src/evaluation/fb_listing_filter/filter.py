"""
FB listing filter — determines if a listing has enough information for eBay comparison.

Rejects vague listings (e.g. "Messenger bag" with no brand) so we do not waste API calls.
"""

import os
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_warning
from src.evaluation.fb_listing_filter.prompts import (
    SYSTEM_MESSAGE,
    format_fb_listing_for_prompt,
    get_pre_filtering_prompt,
)
from src.evaluation.openai_client import create_sync_response, extract_response_output_text, try_parse_json_dict

logger = setup_colored_logger("fb_listing_filter")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
FILTER_MAX_OUTPUT_TOKENS = 500

# Common placeholder prices (e.g. "contact for price" listings)
_INVALID_PRICES = (123, 1234, 12345, 123456, 1234567, 12345678, 123456789)


def is_suspicious_price(price: Optional[float]) -> bool:
    """Return True if the price is suspicious (free, zero, or placeholder)."""
    if price is None:
        return True
    if price <= 0:
        return True
    return price in _INVALID_PRICES


def filter_fb_listing(listing: Listing) -> Optional[str]:
    """
    Determine if a FB listing has enough information for eBay comparison.

    Returns None if accepted. Returns reject reason string if rejected.
    On API or parse failure, returns None (fail open).
    """
    if not OpenAI or not OPENAI_API_KEY:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)
    prompt = get_pre_filtering_prompt(fb_listing_text, product_recon_json="")

    try:
        response = create_sync_response(
            client,
            instructions=SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=FILTER_MAX_OUTPUT_TOKENS,
        )
        raw = extract_response_output_text(response)
        result = try_parse_json_dict(raw)
        if result is None:
            logger.debug(f"Filter response was not valid JSON: {raw or '(empty)'}")
            return None
        if result.get("rejected"):
            reason = result.get("reason", "insufficient information")
            logger.debug(f"Listing rejected: {reason}")
            return reason
        logger.debug(f"Listing accepted: {result.get('reason', '')}")
        return None
    except Exception as e:
        log_warning(logger, f"FB listing filter API call failed: {e}")
        return None
