"""
FB listing filter — determines if a listing has enough information for eBay comparison.

Rejects vague listings (e.g. "Messenger bag" with no brand) so we do not waste API calls.
Includes rule-based filtering (Gate 1a) and lightweight LLM filtering (Gate 1b).
"""

import os
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_warning
from src.evaluation.listing_format import format_fb_listing_for_prompt
from src.evaluation.fb_listing_filter.prompts import (
    SYSTEM_MESSAGE,
    get_pre_filtering_prompt,
)
from src.evaluation.openai_client import create_sync_response, extract_response_output_text, try_parse_json_dict

logger = setup_colored_logger("fb_listing_filter")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
FILTER_MAX_OUTPUT_TOKENS = 500
# Use a cheaper/faster model for pre-recon filtering
PRE_RECON_FILTER_MODEL = "gpt-4o-mini"

# Common placeholder prices (e.g. "contact for price" listings)
_INVALID_PRICES = (123, 1234, 12345, 123456, 1234567, 12345678, 123456789)


def is_suspicious_price(price: Optional[float]) -> bool:
    """Return True if the price is suspicious (free, zero, or placeholder)."""
    if price is None:
        return True
    if price <= 0:
        return True
    return price in _INVALID_PRICES


def _should_reject_by_rules(listing: Listing) -> Optional[str]:
    """
    Rule-based pre-filter: reject listings that appear to be from buyers or have suspicious prices.
    
    Checks:
    1. Suspicious prices (free, zero, placeholder prices)
    2. Buyer keywords in title ("wanted", "looking for", "ISO", "WTB")
    
    This is Gate 1a of the pre-recon filtering stage.
    
    Returns:
        Rejection reason string if listing should be rejected, None otherwise.
    """
    # Check for suspicious prices first
    if is_suspicious_price(listing.price):
        return "Suspicious price (free, zero, or placeholder)"
    
    # Check for buyer keywords
    title_lower = listing.title.lower()
    buyer_keywords = ["wanted", "looking for", "iso", "wtb"]
    for keyword in buyer_keywords:
        if keyword in title_lower:
            return f"Listing appears to be from a buyer (contains '{keyword}')"
    return None


def filter_fb_listing(listing: Listing) -> Optional[str]:
    """
    Determine if a FB listing has enough information for eBay comparison.

    Returns None if accepted. Returns reject reason string if rejected.
    On API or parse failure, returns None (fail open).
    """
    # Gate 1a: Rule-based pre-filter (no LLM)
    rule_reject_reason = _should_reject_by_rules(listing)
    if rule_reject_reason is not None:
        logger.debug(f"Pre-recon filter (rules) rejected: {rule_reject_reason}")
        return rule_reject_reason

    # Gate 1b: Pre-Recon Filter (lightweight LLM)
    if not OpenAI or not OPENAI_API_KEY:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)
    prompt = get_pre_filtering_prompt(fb_listing_text)

    try:
        response = create_sync_response(
            client,
            instructions=SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=FILTER_MAX_OUTPUT_TOKENS,
            model=PRE_RECON_FILTER_MODEL,
        )
        raw = extract_response_output_text(response)
        result = try_parse_json_dict(raw)
        if result is None:
            logger.debug(f"Pre-recon filter response was not valid JSON: {raw or '(empty)'}")
            # Continue on error (fail-open for pre-recon filter)
            return None
        if result.get("rejected"):
            reason = result.get("reason", "insufficient information")
            logger.debug(f"Pre-recon filter rejected: {reason}")
            return reason
        logger.debug(f"Pre-recon filter accepted: {result.get('reason', '')}")
        return None
    except Exception as e:
        log_warning(logger, f"Pre-recon filter API call failed: {e}")
        # Continue on error (fail-open for pre-recon filter)
        return None
