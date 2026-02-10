"""
OpenAI API helper functions for query generation and result filtering.

Provides helper functions for making OpenAI API calls to generate optimized eBay
search queries and filter eBay results to match Facebook Marketplace listings.
"""

import os
import json
import re
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
    get_result_filtering_prompt,
)

logger = setup_colored_logger("openai_helpers")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str
) -> Optional[Tuple[str, Optional[dict]]]:
    """
    Generate an optimized eBay search query and optional Browse API parameters for a FB listing.
    Returns (enhanced_query, browse_api_parameters) or None if the library is missing, API key is unset, or the call fails.
    """
    if not OpenAI:
        logger.error("Search suggestions unavailable (required package not installed).")
        return None
    if not OPENAI_API_KEY:
        logger.warning("Search suggestions not available (missing configuration).")
        return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    description_text = listing.description if listing.description else "No description provided"
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
            "max_tokens": 200,
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
            logger.debug(f"eBay search suggestion (preview):\n{truncated_content}")
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
        logger.debug(f"Search: '{enhanced_query}'")
        return (enhanced_query, browse_api_parameters)
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
    
    if not ebay_items or len(ebay_items) == 0:
        return ([], ebay_items, {})
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    description_text = listing.description if listing.description else "No description provided"
    
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
        
        # Log full response for debugging
        try:
            if hasattr(response, 'model_dump'):
                response_dict = response.model_dump()
            elif hasattr(response, 'dict'):
                response_dict = response.dict()
            else:
                response_dict = {
                    "id": getattr(response, 'id', None),
                    "model": getattr(response, 'model', None),
                    "choices": [{
                        "message": {
                            "content": response.choices[0].message.content if response.choices else None
                        }
                    }]
                }
            
            # Access dictionary with bracket notation, not dot notation
            if response_dict and "choices" in response_dict and len(response_dict["choices"]) > 0:
                raw_content = response_dict["choices"][0]["message"]["content"]
                truncated_content = truncate_lines(raw_content, 5)
                logger.debug(f"Match result (preview):\n{truncated_content}")
            else:
                logger.debug("Match result: no content")
        except Exception as e:
            logger.debug(f"Could not show match preview: {e}")
        
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON with better error handling
        try:
            result = json.loads(content)
        except json.JSONDecodeError as json_err:
            error_line = getattr(json_err, "lineno", None)
            error_col = getattr(json_err, "colno", None)

            # Try to extract what we can - look for comparable_indices even in malformed JSON
            indices_match = re.search(r'"comparable_indices"\s*:\s*\[([\d\s,]+)\]', content)
            if indices_match:
                try:
                    indices_str = indices_match.group(1)
                    comparable_indices = [int(x.strip()) for x in indices_str.split(",") if x.strip()]
                    loc = f" line {error_line}, col {error_col}" if error_line else ""
                    logger.warning(f"Match check had a glitch; still used {len(comparable_indices)} matching listings.")
                    
                    # Try to extract reasons dict - look for complete key-value pairs
                    reasons = {}
                    reasons_match = re.search(r'"reasons"\s*:\s*\{', content)
                    if reasons_match:
                        # Find the start of the reasons dict
                        reasons_start = reasons_match.end()
                        # Try to extract complete key-value pairs
                        # Pattern: "key": "value" (handling escaped quotes)
                        reason_pattern = r'"(\d+)"\s*:\s*"((?:[^"\\]|\\.)*)"'
                        for match in re.finditer(reason_pattern, content[reasons_start:]):
                            key = match.group(1)
                            value = match.group(2)
                            # Unescape JSON escape sequences
                            value = value.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                            reasons[key] = value
                        
                        if reasons:
                            logger.debug(f"Recovered {len(reasons)} reasons")
                        else:
                            logger.debug("Could not recover reasons")
                except ValueError:
                    logger.warning("Could not recover matching listings")
                    return None
            else:
                logger.warning("Could not find matches in response — using all listings")
                return None
        else:
            # Successfully parsed JSON
            comparable_indices = result.get("comparable_indices", [])
            reasons = result.get("reasons", {})
        
        if not isinstance(comparable_indices, list):
            logger.warning("Match list invalid — skipping filter")
            return None
        
        if not isinstance(reasons, dict):
            logger.debug("No reasons returned")
            reasons = {}
        
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
        
        expected_reason_count = len(ebay_items)
        actual_reason_count = len(reasons)
        if actual_reason_count < expected_reason_count:
            missing_count = expected_reason_count - actual_reason_count
            logger.warning(f"Missing reasons for {missing_count} items — comparison list may be incomplete.")

        if reasons:
            logger.debug(f"Why items were dropped (sample):")
            for idx, reason in list(reasons.items())[:3]:
                logger.debug(f"   {idx}: {reason}")
        
        return (comparable_indices, filtered_items, reasons)
        
    except json.JSONDecodeError as e:
        # This should not happen now since we handle it above, but keep as fallback
        logger.warning("Could not read match result — using all listings")
        return None
    except Exception as e:
        logger.warning(f"Match check failed: {e} — using all listings")
        return None
