"""
Internet enrichment — uses web search to identify product details from a FB listing.

Produces structured product recon (brand, model, category, etc.) used by eBay query
generation and result filtering.
"""

import json
import os
from typing import Callable, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_error_short, log_warning
from src.evaluation.internet_enrichment.prompts import (
    SYSTEM_MESSAGE,
    format_fb_listing_for_prompt,
    get_internet_product_recon_prompt,
)
from src.evaluation.openai_client import (
    create_sync_response,
    extract_response_output_text,
    extract_url_citations,
    try_parse_json_dict,
)

logger = setup_colored_logger("internet_enrichment")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PRODUCT_RECON_MAX_OUTPUT_TOKENS = 1000
PRODUCT_RECON_RETRY_MAX_OUTPUT_TOKENS = 1500
PRODUCT_RECON_WEB_TOOLS = [{"type": "web_search"}]


def enrich_listing_with_internet(
    listing: Listing,
    on_product_recon: Optional[Callable[[dict, list[dict]], None]] = None,
) -> Optional[str]:
    """
    Use internet search to identify product details from a FB listing.

    Returns product_recon_json string, or None on failure.
    Calls on_product_recon(recon_result, citations) if provided and successful.
    """
    if not OpenAI or not OPENAI_API_KEY:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    fb_listing_text = format_fb_listing_for_prompt(listing)
    prompt = get_internet_product_recon_prompt(fb_listing_text)

    try:
        recon_result = None
        recon_citations: list[dict] = []
        recon_raw = ""

        for attempt_idx in range(2):
            max_tokens = (
                PRODUCT_RECON_MAX_OUTPUT_TOKENS if attempt_idx == 0 else PRODUCT_RECON_RETRY_MAX_OUTPUT_TOKENS
            )
            response = create_sync_response(
                client,
                instructions=SYSTEM_MESSAGE,
                prompt=prompt,
                max_output_tokens=max_tokens,
                tools=PRODUCT_RECON_WEB_TOOLS,
                request_overrides={
                    "reasoning": {"effort": "low"},
                    "text": {"verbosity": "low"},
                },
            )
            recon_citations = extract_url_citations(response)
            recon_raw = extract_response_output_text(response)
            recon_result = try_parse_json_dict(recon_raw)
            if recon_result is not None:
                break

            status = getattr(response, "status", None)
            incomplete_details = getattr(response, "incomplete_details", None)
            incomplete_reason = getattr(incomplete_details, "reason", None) if incomplete_details else None
            if status == "incomplete" and incomplete_reason == "max_output_tokens" and attempt_idx == 0:
                log_warning(logger, "Product research ran out of room — retrying with more tokens")
                continue

            log_error_short(logger, "Product research response was invalid JSON")
            logger.debug(f"Product research response text: {recon_raw if recon_raw else '(empty)'}")
            return None

        key_attributes = recon_result.get("key_attributes", [])
        if isinstance(key_attributes, list) and len(key_attributes) > 0:
            key_attributes_text = ", ".join(
                f"{attr.get('attribute', 'unknown')}: {attr.get('value', 'unknown')} ({attr.get('price_impact', 'unknown')})"
                for attr in key_attributes
                if isinstance(attr, dict)
            ) or "None"
        else:
            key_attributes_text = "None"
        computable = recon_result.get("computable", True)
        logger.debug(" Internet search found:")
        logger.debug(f"  - Product name: {recon_result.get('canonical_name', 'Unknown')}")
        logger.debug(f"  - Brand: {recon_result.get('brand', 'Unknown')}")
        logger.debug(f"  - Category: {recon_result.get('category', 'Unknown')}")
        logger.debug(f"  - Model/series: {recon_result.get('model_or_series', 'Unknown')}")
        logger.debug(f"  - Year/generation: {recon_result.get('year_or_generation', 'Unknown')}")
        logger.debug(f"  - Price-changing details: {key_attributes_text}")
        logger.debug(f"  - Computable: {computable}")
        if not computable:
            logger.debug(f"  - Reject reason: {recon_result.get('reject_reason', 'None')}")
        logger.debug(f"  - Notes: {recon_result.get('notes', '') or 'None'}")
        if recon_citations:
            for c in recon_citations:
                url = (c.get("url", "") or "").strip()
                title = (c.get("title", "") or "").strip()
                if url:
                    logger.debug(f"  - {url}" + (f" — {title}" if title else ""))
        else:
            logger.debug("  - No citations found")

        if on_product_recon is not None:
            try:
                on_product_recon(recon_result, recon_citations)
            except Exception:
                pass  # Ignore callback errors; enrichment result is still valid

        return json.dumps(recon_result, ensure_ascii=True, indent=2)
    except Exception as e:
        logger.debug(f"Product research request failed: {e}")
        return None
