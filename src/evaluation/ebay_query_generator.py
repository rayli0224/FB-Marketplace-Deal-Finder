"""
eBay search query generation from Facebook Marketplace listings.

Uses OpenAI to generate optimized eBay search queries for comparing FB listings
to sold eBay prices. Includes pre-filtering to reject listings that lack enough
detail for a useful comparison.
"""

import json
import os
from typing import Callable, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_error_short, log_warning, truncate_lines
from src.evaluation.prompts import (
    PRE_FILTERING_SYSTEM_MESSAGE,
    PRODUCT_RECON_SYSTEM_MESSAGE,
    QUERY_GENERATION_SYSTEM_MESSAGE,
    format_fb_listing_for_prompt,
    get_internet_product_recon_prompt,
    get_pre_filtering_prompt,
    get_query_generation_prompt,
)
from src.evaluation.openai_client import (
    create_sync_response,
    extract_response_output_text,
    extract_url_citations,
    try_parse_json_dict,
)

logger = setup_colored_logger("ebay_query_generator")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000
PRE_FILTER_MAX_OUTPUT_TOKENS = 500
PRODUCT_RECON_MAX_OUTPUT_TOKENS = 1000
PRODUCT_RECON_WEB_TOOLS = [{"type": "web_search"}]
PRODUCT_RECON_RETRY_MAX_OUTPUT_TOKENS = 1500


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str,
    on_product_recon: Optional[Callable[[dict, list[dict]], None]] = None,
) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
    """
    Generate an optimized eBay search query for a FB listing.
    Returns (enhanced_query, skip_reason, product_recon_json) or None on generic failure.
    On success: (query, None, product_recon_json).
    On model rejection: (None, reason, None).
    On other failure: None.
    """
    if not OpenAI:
        logger.error("❌ Search suggestions unavailable (required package not installed).")
        return None
    if not OPENAI_API_KEY:
        log_warning(logger, "Search suggestions not available (missing configuration).")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)

    try:
        recon_prompt = get_internet_product_recon_prompt(fb_listing_text)
        recon_response = None
        recon_raw = ""
        recon_result = None
        recon_citations: list[dict] = []

        for attempt_idx in range(2):
            max_tokens = (
                PRODUCT_RECON_MAX_OUTPUT_TOKENS
                if attempt_idx == 0
                else PRODUCT_RECON_RETRY_MAX_OUTPUT_TOKENS
            )
            recon_response = create_sync_response(
                client,
                instructions=PRODUCT_RECON_SYSTEM_MESSAGE,
                prompt=recon_prompt,
                max_output_tokens=max_tokens,
                tools=PRODUCT_RECON_WEB_TOOLS,
                request_overrides={
                    # Keep answers short and reduce internal "thinking" so we actually get JSON back.
                    "reasoning": {"effort": "low"},
                    "text": {"verbosity": "low"},
                },
            )

            recon_citations = extract_url_citations(recon_response)

            recon_raw = extract_response_output_text(recon_response)
            recon_result = try_parse_json_dict(recon_raw)
            if recon_result is not None:
                break

            status = getattr(recon_response, "status", None)
            incomplete_details = getattr(recon_response, "incomplete_details", None)
            incomplete_reason = getattr(incomplete_details, "reason", None) if incomplete_details else None

            if status == "incomplete" and incomplete_reason == "max_output_tokens" and attempt_idx == 0:
                log_warning(logger, "Product research ran out of room — trying again with a shorter answer")
                continue

            log_error_short(logger, "Product research response was invalid JSON")
            logger.debug(f"Product research response text: {recon_raw if recon_raw else '(empty)'}")
            if recon_response is not None:
                logger.debug(f"Product research response status: {status or '(unknown)'}")
            return None

        variant_dimensions = recon_result.get("variant_dimensions", [])
        if isinstance(variant_dimensions, list):
            variant_dimensions_text = ", ".join(str(value) for value in variant_dimensions) or "None"
        else:
            variant_dimensions_text = str(variant_dimensions)
        logger.debug(" Internet search found:")
        logger.debug(f"  - Product name: {recon_result.get('canonical_name', 'Unknown')}")
        logger.debug(f"  - Brand: {recon_result.get('brand', 'Unknown')}")
        logger.debug(f"  - Category: {recon_result.get('category', 'Unknown')}")
        logger.debug(f"  - Model/series: {recon_result.get('model_or_series', 'Unknown')}")
        logger.debug(f"  - Year/generation: {recon_result.get('year_or_generation', 'Unknown')}")
        logger.debug(f"  - Price-changing details: {variant_dimensions_text}")
        logger.debug(f"  - Notes: {recon_result.get('notes', '') or 'None'}")

        if recon_citations:
            logger.debug("  - Product research citations:")
            for c in recon_citations:
                url = (c.get("url", "") or "").strip()
                title = (c.get("title", "") or "").strip()
                if not url:
                    continue
                if title:
                    logger.debug(f"  - {url} — {title}")
                else:
                    logger.debug(f"  - {url}")
        else:
            logger.debug("  - No citations found")

        if on_product_recon is not None:
            try:
                on_product_recon(recon_result, recon_citations)
            except Exception:
                pass
        product_recon_json = json.dumps(recon_result, ensure_ascii=True, indent=2)
    except Exception as e:
        logger.debug(f"Product research request failed: {e}")
        return None

    pre_filtering_prompt = get_pre_filtering_prompt(fb_listing_text, product_recon_json)
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
            logger.debug(f"Pre-filter response was not valid JSON: {pre_raw if pre_raw else '(empty)'}")
        elif pre_result.get("rejected"):
            logger.debug(f"Pre-filter rejected: {pre_result.get('reason', 'insufficient information')}")
            return (None, pre_result.get("reason", "insufficient information"), None)
        else:
            logger.debug(f"Pre-filter accepted: {pre_result.get('reason', '')}")
    except Exception as e:
        logger.warning(f"Pre-filter API call failed: {e}")
        pre_result = None

    prompt = get_query_generation_prompt(product_recon_json)

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
        return (enhanced_query, None, product_recon_json)
    except Exception as e:
        log_error_short(logger, f"Search suggestion request failed: {e}")
        return None
