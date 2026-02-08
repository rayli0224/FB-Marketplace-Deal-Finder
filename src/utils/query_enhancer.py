"""
Query enhancer utility for generating eBay search queries using OpenAI.

Takes a Facebook Marketplace listing and generates an optimized eBay search query
with exclusion keywords specific to that listing. This ensures accurate price
comparisons by matching each FB listing to similar items on eBay.
"""

import os
import json
import logging
from typing import Optional, Tuple, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.scrapers.fb_marketplace_scraper import Listing
from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix (auto-detects DEBUG from env/--debug flag)
logger = setup_colored_logger("query_enhancer")

# OpenAI API key from environment
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str
) -> Optional[Tuple[str, List[str]]]:
    """
    Generate an optimized eBay search query and exclusion keywords for a specific FB listing.
    
    Uses OpenAI to analyze the listing title, price, description, and original search query to create
    a targeted eBay search query that will find similar items. Also generates exclusion
    keywords to filter out accessories, broken items, and unrelated listings.
    
    Args:
        listing: Facebook Marketplace listing with title, price, location, url, and description
        original_query: The original user search query (e.g., "nintendo ds")
        
    Returns:
        Tuple of (enhanced_ebay_query, exclusion_keywords) if successful, None if failed.
        Example: ("nintendo ds lite", ["case", "pen", "stylus", "broken"])
        
    Example:
        >>> listing = Listing(
        ...     title="Nintendo DS Lite Pink - Great Condition",
        ...     price=50.0,
        ...     location="New York, NY",
        ...     url="https://facebook.com/...",
        ...     description="Great condition, comes with charger and stylus"
        ... )
        >>> result = generate_ebay_query_for_listing(listing, "nintendo ds")
        >>> enhanced_query, exclusions = result
        >>> print(enhanced_query)  # "nintendo ds lite"
        >>> print(exclusions)  # ["case", "pen", "stylus", "broken", "for parts"]
    """
    if not OpenAI:
        logger.error("OpenAI library not installed. Install with: pip install openai")
        return None
    
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set in environment variables. Skipping query enhancement.")
        return None
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Build prompt for OpenAI
    description_text = listing.description if listing.description else "No description provided"
    prompt = f"""You are helping to find accurate price comparisons on eBay for a Facebook Marketplace listing.

Original user search query: "{original_query}"
Facebook Marketplace listing:
- Title: "{listing.title}"
- Price: ${listing.price:.2f}
- Location: {listing.location}
- Description: "{description_text}"

Your task:
1. Generate an optimized eBay search query that will find similar items to this listing.
2. Provide exclusion keywords to filter out unrelated listings (accessories, incompatible items, etc).

Abstraction rules:

PRESERVE (always include if present):
- Brand
- Product type
- Model / product line
- Functional condition (e.g. "for parts", "broken", "not working", "refurbished", "new")

INCLUDE ONLY IF THEY MATERIALLY AFFECT PRICE:
- Storage / capacity (e.g. 128GB, 1TB)
- Pro/Max/Ultra variants
- Generation / year

IGNORE OR GENERALIZE:
- Color
- Cosmetic descriptors
- Seller adjectives (rare, amazing, mint)
- Minor accessories
- Bundle details unless they dominate value

Important:
- The goal is to find many comparable items, not exact matches.
- Do NOT make the query overly specific.
- However, if the listing is for parts / broken, the query MUST reflect that.
- The enhanced_query should typically be 3–6 tokens long, unless functional condition requires more.

Focus on the MAIN PRODUCT, not accessories.
Examples:
- "Nintendo DS Lite Pink" → "Nintendo DS Lite"
- "iPhone 13 Pro 256GB cracked screen" → "iPhone 13 Pro for parts"
- "MacBook Pro 2019 16 inch i9" → "MacBook Pro 2019"

Return your response as a JSON object with exactly this structure:
{{
  "enhanced_query": "optimized eBay search query",
  "exclusion_keywords": ["keyword1", "keyword2", "keyword3"]
}}

Only return the JSON object, no other text."""

    try:
        messages = [
            {
                "role": "system",
                "content": "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."
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
        
        if not isinstance(exclusion_keywords, list):
            exclusion_keywords = []
        
        logger.info(f"Generated eBay query: '{enhanced_query}' | Exclusions: {exclusion_keywords}")
        
        return (enhanced_query, exclusion_keywords)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        logger.debug(f"Response content: {content}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return None
