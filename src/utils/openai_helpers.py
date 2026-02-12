"""
OpenAI API helper functions for query generation and result filtering.

Provides helper functions for making OpenAI API calls to generate optimized eBay
search queries and filter eBay results to match Facebook Marketplace listings.
"""

import os
import json
from typing import Optional, Tuple, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger, log_error_short, truncate_lines
from src.utils.prompts import (
    QUERY_GENERATION_SYSTEM_MESSAGE,
    RESULT_FILTERING_SYSTEM_MESSAGE,
    get_query_generation_prompt,
    get_pre_filtering_prompt,
    get_result_filtering_prompt,
)

logger = setup_colored_logger("openai_helpers")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


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
    
    description_text = listing.description if listing.description else ""
    
    pre_filtering_prompt = get_pre_filtering_prompt(
        listing_title=listing.title,
        listing_price=listing.price,
        listing_location=listing.location,
        description_text=description_text,
    )
    pre_filtering_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": pre_filtering_prompt
            },
        ],
    )
    raw_pre = pre_filtering_response.choices[0].message.content or ""
    pre_content = raw_pre.strip()
    if pre_content.startswith("```"):
        pre_content = pre_content.split("```", 2)[1]
        if pre_content.startswith("json"):
            pre_content = pre_content[4:]
    pre_content = pre_content.strip()
    try:
        pre_result = json.loads(pre_content)
        if pre_result.get("rejected"):
            logger.debug(f"Pre-filter for FB listing rejected:\n\t{pre_result.get('reason', 'insufficient information')}")
            return None, None, pre_result.get("reason", "insufficient information")
        logger.debug(f"Pre-filter for FB listing accepted:\n\t{pre_result.get('reason', '')}")
    except json.JSONDecodeError:
        pass
    
    prompt = get_query_generation_prompt(
        listing_title=listing.title,
        listing_price=listing.price,
        listing_location=listing.location,
        description_text=description_text,
    )

    try:
        messages = [
            {
                "role": "system",
                "content": QUERY_GENERATION_SYSTEM_MESSAGE
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        api_params = {
            "model": "gpt-4o-mini",
            "temperature": 0.4,
            "max_tokens": 1000,
        }
        
        response = client.chat.completions.create(
            model=api_params["model"],
            messages=messages,
            temperature=api_params["temperature"],
            max_tokens=api_params["max_tokens"],
        )
        raw_content = response.choices[0].message.content
        try:
            truncated_content = truncate_lines(raw_content, 5)
            logger.debug(f"eBay search suggestion (preview):\n\t{truncated_content}")
        except Exception as e:
            logger.debug(f"Could not show preview: {e}")
        
        content = raw_content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        result = json.loads(content)
        enhanced_query = result.get("enhanced_query", original_query)
        browse_api_parameters = result.get("browse_api_parameters")
        if not isinstance(browse_api_parameters, dict):
            browse_api_parameters = None
        else:
            # Remove `filter: conditionIds:{{1000|3000}}` from the browse_api_parameters for now
            browse_api_parameters = {k: v for k, v in browse_api_parameters.items() if k != "filter"}
        logger.debug(f"Search: '{enhanced_query}'")
        return (enhanced_query, browse_api_parameters, None)
    except json.JSONDecodeError as e:
        log_error_short(logger, f"Search suggestion response was invalid: {e}")
        logger.debug(f"Response content: {content}")
        return None
    except Exception as e:
        log_error_short(logger, f"Search suggestion request failed: {e}")
        return None


def filter_ebay_results_with_openai(
    listing: Listing,
    ebay_items: List[dict]
) -> Optional[Tuple[List[int], List[dict], dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.
    
    Uses OpenAI to analyze each eBay item's title, description, and condition and compare them
    to the FB listing's title, description, and price. Removes items that are accessories,
    different models, or otherwise not comparable. This improves price comparison accuracy by
    ensuring only truly similar items are used for calculating the market average.
    
    Returns tuple of (comparable_indices, filtered list of eBay items, reasons dict) or None if filtering fails.
    comparable_indices is a list of 1-based indices of items that passed filtering.
    The reasons dict maps 1-based item indices to short reason strings explaining accept/reject decisions.
    Format: [1, 3, 5], [{title, price, url}, ...], {"1": "reason", "2": "reason", ...}
    """
    if not OpenAI:
        logger.debug("Search suggestions unavailable — skipping match filter")
        return None
    if not OPENAI_API_KEY:
        logger.debug("Search suggestions not configured — skipping match filter")
        return None
    
    if not ebay_items:
        return ([], ebay_items, {})
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    description_text = listing.description if listing.description else ""
    
    # Format eBay items with enhanced details (description, condition) if available
    ebay_items_text_parts = []
    for i, item in enumerate(ebay_items):
        title = item.get('title', '')
        price = item.get('price', 0)
        description = item.get('description', '')
        condition = item.get('condition', '')
        
        item_text = f"{i+1}. {title} - ${price:.2f}"
        if condition:
            item_text += f" | Condition: {condition}"
        if description:
            # Truncate description to avoid overly long prompts
            desc_preview = description[:200] + "..." if len(description) > 200 else description
            item_text += f"\n   Description: {desc_preview}"
        
        ebay_items_text_parts.append(item_text)
    
    ebay_items_text = "\n".join(ebay_items_text_parts)
    num_items = len(ebay_items)
    
    prompt = get_result_filtering_prompt(
        listing_title=listing.title,
        listing_price=listing.price,
        description_text=description_text,
        ebay_items_text=ebay_items_text,
        num_items=num_items,
    )
    
    try:
        messages = [
            {
                "role": "system",
                "content": RESULT_FILTERING_SYSTEM_MESSAGE
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Calculate max_tokens based on number of items to avoid truncation
        # Each item needs ~60 tokens for its reason string, plus JSON structure overhead
        # Use a minimum of 2000 tokens, or 60 tokens per item, whichever is higher
        # This ensures we have enough tokens for reasons for ALL items (not just comparable ones)
        max_tokens = max(2000, num_items * 60)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        
        raw_content = response.choices[0].message.content or ""
        try:
            logger.debug(f"Match result (preview):\n{truncate_lines(raw_content, 5)}")
        except Exception:
            pass

        content = raw_content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Match result was invalid JSON — using all listings without filtering")
            logger.debug(f"Match result: {content}")
            return None

        results_list = result.get("results", [])
        if not isinstance(results_list, list) or len(results_list) != num_items:
            logger.warning("Match result format invalid — using all listings without filtering")
            logger.debug(f"Match result: {content}")
            return None

        comparable_indices = [
            i + 1
            for i, r in enumerate(results_list)
            if isinstance(r, dict) and r.get("rejected") is False
        ]
        reasons = {
            str(i + 1): r.get("reason", "") if isinstance(r, dict) else ""
            for i, r in enumerate(results_list)
        }

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
            logger.debug(f"Why items were dropped (first 3):")
            for idx, reason in list(reasons.items())[:3]:
                logger.debug(f"   {idx}: {reason}")
        
        return (comparable_indices, filtered_items, reasons)

    except Exception as e:
        logger.warning(f"Match check failed: {e} — using all listings")
        return None
