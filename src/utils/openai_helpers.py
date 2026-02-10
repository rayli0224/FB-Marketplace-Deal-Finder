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
        logger.error("OpenAI library not installed — pip install openai")
        return None
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — skipping query enhancement")
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
            logger.debug(f"OpenAI API Response - Message content (first 5 lines):\n{truncated_content}")
        except Exception as e:
            logger.debug(f"OpenAI API Response - Could not extract content: {e}")
        
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
        logger.info(f"eBay query: '{enhanced_query}'")
        if browse_api_parameters:
            logger.debug(f"Browse API parameters: {browse_api_parameters}")
        return (enhanced_query, browse_api_parameters)
    except json.JSONDecodeError as e:
        log_error_short(logger, f"Parse OpenAI response JSON: {e}")
        logger.debug(f"Response content: {content}")
        return None
    except Exception as e:
        log_error_short(logger, f"OpenAI API call failed: {e}")
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
        logger.debug("OpenAI library not installed - skipping eBay result filtering")
        return None
    
    if not OPENAI_API_KEY:
        logger.debug("OPENAI_API_KEY not set - skipping eBay result filtering")
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
    
    prompt = get_result_filtering_prompt(
        listing_title=listing.title,
        listing_price=listing.price,
        description_text=description_text,
        ebay_items_text=ebay_items_text,
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
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=1000,
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
                logger.debug(f"OpenAI Filtering Response - Raw content (first 5 lines):\n{truncated_content}")
            else:
                logger.debug(f"OpenAI Filtering Response - Response structure: {json.dumps(response_dict, indent=2)}")
        except Exception as e:
            logger.debug(f"OpenAI Filtering Response - Could not serialize response: {e}")
            logger.debug(f"OpenAI Filtering Response - Raw response: {str(response)}")
        
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
            # Log the error location and surrounding content
            error_line = getattr(json_err, 'lineno', None)
            error_col = getattr(json_err, 'colno', None)
            error_pos = getattr(json_err, 'pos', None)
            
            logger.warning(f"Failed to parse OpenAI filter response as JSON: {json_err}")
            logger.warning(f"Full response content: {content}")
            if error_line:
                content_lines = content.split('\n')
                logger.warning(f"Error at line {error_line}, column {error_col}")
                # Show context around the error
                start_line = max(0, error_line - 3)
                end_line = min(len(content_lines), error_line + 2)
                logger.warning(f"Content around error (lines {start_line + 1}-{end_line}):")
                for i in range(start_line, end_line):
                    marker = ">>> " if i == error_line - 1 else "    "
                    logger.warning(f"{marker}{i + 1}: {content_lines[i]}")
            elif error_pos:
                # Show content around the error position
                start_pos = max(0, error_pos - 100)
                end_pos = min(len(content), error_pos + 100)
                logger.warning(f"Content around error position {error_pos}:")
                logger.warning(f"  ...{content[start_pos:end_pos]}...")
            else:
                # Fallback: show first 500 chars
                logger.warning(f"Content preview (first 500 chars): {content[:500]}")
            
            # Try to extract what we can - look for comparable_indices even in malformed JSON
            indices_match = re.search(r'"comparable_indices"\s*:\s*\[([\d\s,]+)\]', content)
            if indices_match:
                try:
                    indices_str = indices_match.group(1)
                    comparable_indices = [int(x.strip()) for x in indices_str.split(',') if x.strip()]
                    logger.info(f"Recovered comparable_indices from malformed JSON: {comparable_indices}")
                    
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
                            logger.debug(f"Recovered {len(reasons)} reasons from malformed JSON")
                        else:
                            logger.debug("Could not recover reasons from malformed JSON")
                except ValueError:
                    logger.warning("Could not recover comparable_indices from malformed JSON")
                    return None
            else:
                logger.warning("Could not find comparable_indices in malformed JSON - using original items")
                return None
        else:
            # Successfully parsed JSON
            comparable_indices = result.get("comparable_indices", [])
            reasons = result.get("reasons", {})
        
        if not isinstance(comparable_indices, list):
            logger.warning("OpenAI returned invalid comparable_indices format - skipping filter")
            return None
        
        if not isinstance(reasons, dict):
            logger.debug("OpenAI did not return reasons dict - continuing without reasons")
            reasons = {}
        
        # Filter items (indices are 1-based, convert to 0-based)
        filtered_items = [
            ebay_items[idx - 1]
            for idx in comparable_indices
            if 1 <= idx <= len(ebay_items)
        ]
        
        removed_count = len(ebay_items) - len(filtered_items)
        if removed_count > 0:
            logger.info(f"Filtered out {removed_count} non-comparable ({len(filtered_items)} remaining)")
        else:
            logger.debug(f"All {len(ebay_items)} eBay items were deemed comparable")
        
        # Log reasons for debugging
        if reasons:
            logger.debug(f"Received reasons for {len(reasons)} items. First 3 reasons:")
            for idx, reason in list(reasons.items())[:3]:  # Log first 3 reasons
                logger.debug(f"   Item {idx}: {reason}")
        
        return (comparable_indices, filtered_items, reasons)
        
    except json.JSONDecodeError as e:
        # This should not happen now since we handle it above, but keep as fallback
        logger.warning(f"Failed to parse OpenAI filter response as JSON: {e} - using original items")
        return None
    except Exception as e:
        logger.warning(f"OpenAI filtering failed: {e} — using original items")
        return None
