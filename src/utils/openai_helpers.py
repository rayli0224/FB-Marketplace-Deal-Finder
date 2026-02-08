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
from src.utils.colored_logger import setup_colored_logger
from src.utils.prompts import (
    QUERY_GENERATION_SYSTEM_MESSAGE,
    RESULT_FILTERING_SYSTEM_MESSAGE,
    get_query_generation_prompt,
    get_result_filtering_prompt,
)

# Configure colored logging with module prefix (auto-detects DEBUG from env/--debug flag)
logger = setup_colored_logger("openai_helpers")

# OpenAI API key from environment
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str
) -> Optional[Tuple[str, List[str], Optional[dict]]]:
    """
    Generate an optimized eBay search query and exclusion keywords for a specific FB listing.
    
    Uses OpenAI to analyze the listing title, price, description, and original search query to create
    a targeted eBay search query that will find similar items. Also generates exclusion
    keywords to filter out accessories, broken items, and unrelated listings. May also return
    Browse API parameters (filter, marketplace, sort, limit) for improved search quality.
    
    Args:
        listing: Facebook Marketplace listing with title, price, location, url, and description
        original_query: The original user search query (e.g., "nintendo ds")
        
    Returns:
        Tuple of (enhanced_ebay_query, exclusion_keywords, browse_api_parameters) if successful, None if failed.
        browse_api_parameters is a dict with optional keys: filter, marketplace, sort, limit
        Example: ("nintendo ds lite", ["case", "pen", "stylus", "broken"], {"filter": "price:[25..75]", "marketplace": "EBAY_US"})
        
    Example:
        >>> listing = Listing(
        ...     title="Nintendo DS Lite Pink - Great Condition",
        ...     price=50.0,
        ...     location="New York, NY",
        ...     url="https://facebook.com/...",
        ...     description="Great condition, comes with charger and stylus"
        ... )
        >>> result = generate_ebay_query_for_listing(listing, "nintendo ds")
        >>> enhanced_query, exclusions, api_params = result
        >>> print(enhanced_query)  # "nintendo ds lite"
        >>> print(exclusions)  # ["case", "pen", "stylus", "broken", "for parts"]
        >>> print(api_params)  # {"filter": "price:[25..75]", "marketplace": "EBAY_US", "sort": "bestMatch", "limit": 50}
    """
    if not OpenAI:
        logger.error("OpenAI library not installed. Install with: pip install openai")
        return None
    
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set in environment variables. Skipping query enhancement.")
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
        
        # Log the prompt being sent (INFO level for visibility)
        logger.debug(f"📝 Prompt sent to OpenAI (model: {api_params['model']}):")
        logger.debug(f"   System message: {messages[0]['content']}")
        logger.debug(f"   User prompt ({len(messages[1]['content'])} chars):")
        # Log the full user prompt, but break it into readable chunks
        user_prompt = messages[1]['content']
        prompt_lines = user_prompt.split('\n')
        for line in prompt_lines[:10]:  # Show first 10 lines
            logger.debug(f"      {line}")
        if len(prompt_lines) > 10:
            logger.debug(f"      ... ({len(prompt_lines) - 10} more lines)")
        logger.debug(f"Full messages JSON: {json.dumps(messages, indent=2)}")
        
        response = client.chat.completions.create(
            model=api_params["model"],
            messages=messages,
            temperature=api_params["temperature"],
            max_tokens=api_params["max_tokens"],
        )
        
        # Log full response for debugging
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
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        result = json.loads(content)
        
        enhanced_query = result.get("enhanced_query", original_query)
        exclusion_keywords = result.get("exclusion_keywords", [])
        browse_api_parameters = result.get("browse_api_parameters")
        
        if not isinstance(exclusion_keywords, list):
            exclusion_keywords = []
        
        if not isinstance(browse_api_parameters, dict):
            browse_api_parameters = None
        
        logger.info(f"✅ Generated eBay query: '{enhanced_query}'")
        logger.debug(f"   Exclusions: {exclusion_keywords}")
        if browse_api_parameters:
            logger.debug(f"   Browse API parameters:")
            if browse_api_parameters.get("filter"):
                logger.debug(f"      Filter: {browse_api_parameters['filter']}")
            if browse_api_parameters.get("marketplace"):
                logger.debug(f"      Marketplace: {browse_api_parameters['marketplace']}")
            if browse_api_parameters.get("sort"):
                logger.debug(f"      Sort: {browse_api_parameters['sort']}")
            if browse_api_parameters.get("limit"):
                logger.debug(f"      Limit: {browse_api_parameters['limit']}")
            logger.debug(f"   Full browse_api_parameters: {json.dumps(browse_api_parameters, indent=2)}")
        else:
            logger.debug("   No browse_api_parameters provided by OpenAI")
        
        return (enhanced_query, exclusion_keywords, browse_api_parameters)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        logger.debug(f"Response content: {content}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return None


def filter_ebay_results_with_openai(
    listing: Listing,
    ebay_items: List[dict]
) -> Optional[List[dict]]:
    """
    Filter eBay search results to keep only items comparable to the Facebook Marketplace listing.
    
    Uses OpenAI to analyze each eBay item's title and compare it to the FB listing's title,
    description, and price. Removes items that are accessories, different models, or otherwise
    not comparable. This improves price comparison accuracy by ensuring only truly similar items
    are used for calculating the market average.
    
    Returns filtered list of eBay items (same format: [{title, price, url}, ...]) or None if
    filtering fails (caller should fall back to original items).
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
    
    # Build list of eBay items for the prompt
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
        
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # Parse JSON
        result = json.loads(content)
        comparable_indices = result.get("comparable_indices", [])
        
        if not isinstance(comparable_indices, list):
            logger.warning("OpenAI returned invalid comparable_indices format - skipping filter")
            return ebay_items
        
        # Filter items (indices are 1-based, convert to 0-based)
        filtered_items = [
            ebay_items[idx - 1]
            for idx in comparable_indices
            if 1 <= idx <= len(ebay_items)
        ]
        
        removed_count = len(ebay_items) - len(filtered_items)
        if removed_count > 0:
            logger.info(f"Filtered out {removed_count} non-comparable eBay items ({len(filtered_items)} remaining)")
        else:
            logger.debug(f"All {len(ebay_items)} eBay items were deemed comparable")
        
        return filtered_items if filtered_items else ebay_items
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse OpenAI filter response as JSON: {e} - using original items")
        return None
    except Exception as e:
        logger.warning(f"OpenAI filtering failed: {e} - using original items")
        return None
