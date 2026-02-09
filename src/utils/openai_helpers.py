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
from src.utils.colored_logger import setup_colored_logger, log_error_short
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
) -> Optional[Tuple[str, List[str]]]:
    """
    Generate an optimized eBay search query and exclusion keywords for a specific FB listing.
    Uses OpenAI to analyze the listing title, price, description, and original query; returns
    (enhanced_query, exclusion_keywords) or None if the library is missing, API key is unset, or the call fails.
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
        original_query=original_query,
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
        
        logger.debug(f"OpenAI API Request - Model: {api_params['model']}, Messages: {json.dumps(messages, indent=2)}")
        
        response = client.chat.completions.create(
            model=api_params["model"],
            messages=messages,
            temperature=api_params["temperature"],
            max_tokens=api_params["max_tokens"],
        )
        try:
            if hasattr(response, 'model_dump'):
                response_dict = response.model_dump()
            elif hasattr(response, 'dict'):
                response_dict = response.dict()
            else:
                response_dict = {"id": getattr(response, 'id', None), "model": getattr(response, 'model', None), "choices": [{"message": {"content": response.choices[0].message.content if response.choices else None}}]}
            logger.debug(f"OpenAI API Response - Full response: {json.dumps(response_dict, indent=2)}")
        except Exception as e:
            logger.debug(f"OpenAI API Response - Could not serialize response: {e}")
            logger.debug(f"OpenAI API Response - Raw response: {str(response)}")
        content = response.choices[0].message.content.strip()
        # Strip markdown code fences if OpenAI wrapped the JSON
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        result = json.loads(content)
        enhanced_query = result.get("enhanced_query", original_query)
        exclusion_keywords = result.get("exclusion_keywords", [])
        
        if not isinstance(exclusion_keywords, list):
            exclusion_keywords = []
        
        logger.info(f"eBay query: '{enhanced_query}' | exclusions: {exclusion_keywords}")
        
        return (enhanced_query, exclusion_keywords)
        
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
) -> Optional[List[dict]]:
    """
    Filter eBay results to items comparable to the FB listing using OpenAI. Compares each item's
    title to the listing title, description, and price; drops accessories, different models, and
    non-comparable items. Returns filtered list (same format as input) or None on failure (caller
    may fall back to original list).
    """
    if not OpenAI:
        logger.debug("OpenAI library not installed - skipping eBay result filtering")
        return None
    
    if not OPENAI_API_KEY:
        logger.debug("OPENAI_API_KEY not set - skipping eBay result filtering")
        return None
    
    if not ebay_items or len(ebay_items) == 0:
        return ebay_items
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    description_text = listing.description if listing.description else "No description provided"
    ebay_items_text = "\n".join([
        f"{i+1}. {item.get('title', '')} - ${item.get('price', 0):.2f}"
        for i, item in enumerate(ebay_items)
    ])
    
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
            max_tokens=500,
        )
        
        content = response.choices[0].message.content.strip()
        
        # Strip markdown code fences if OpenAI wrapped the JSON
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        result = json.loads(content)
        comparable_indices = result.get("comparable_indices", [])
        
        if not isinstance(comparable_indices, list):
            logger.warning("Invalid comparable_indices — skipping filter")
            return ebay_items
        
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
        
        return filtered_items if filtered_items else ebay_items
        
    except json.JSONDecodeError as e:
        logger.warning(f"Parse filter response JSON failed: {e} — using original items")
        return None
    except Exception as e:
        logger.warning(f"OpenAI filtering failed: {e} — using original items")
        return None
