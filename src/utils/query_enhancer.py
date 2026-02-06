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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI API key from environment
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str
) -> Optional[Tuple[str, List[str]]]:
    """
    Generate an optimized eBay search query and exclusion keywords for a specific FB listing.
    
    Uses OpenAI to analyze the listing title, price, and original search query to create
    a targeted eBay search query that will find similar items. Also generates exclusion
    keywords to filter out accessories, broken items, and unrelated listings.
    
    Args:
        listing: Facebook Marketplace listing with title, price, location, and url
        original_query: The original user search query (e.g., "nintendo ds")
        
    Returns:
        Tuple of (enhanced_ebay_query, exclusion_keywords) if successful, None if failed.
        Example: ("nintendo ds lite pink console", ["case", "pen", "stylus", "broken"])
        
    Example:
        >>> listing = Listing(
        ...     title="Nintendo DS Lite Pink - Great Condition",
        ...     price=50.0,
        ...     location="New York, NY",
        ...     url="https://facebook.com/..."
        ... )
        >>> result = generate_ebay_query_for_listing(listing, "nintendo ds")
        >>> enhanced_query, exclusions = result
        >>> print(enhanced_query)  # "nintendo ds lite pink console"
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
    prompt = f"""You are helping to find accurate price comparisons on eBay for a Facebook Marketplace listing.

Original user search query: "{original_query}"
Facebook Marketplace listing:
- Title: "{listing.title}"
- Price: ${listing.price:.2f}
- Location: {listing.location}

Your task:
1. Generate an optimized eBay search query that will find similar items to this listing
2. Provide exclusion keywords to filter out any unrelated listing such as accessories, broken items, or parts-only items

Focus on finding the MAIN PRODUCT, not accessories (unless specifically requested in the original query). For example:
- If listing is "Nintendo DS Lite Pink", search for the console itself, not cases or pens
- If listing is "iPhone 13 Pro", search for the phone, not cases or chargers
- Exclude keywords like: "case", "pen", "stylus", "charger", "broken", "for parts", "not working"

Return your response as a JSON object with this exact structure:
{{
    "enhanced_query": "optimized search query for eBay",
    "exclusion_keywords": ["keyword1", "keyword2", "keyword3"]
}}

Only return the JSON object, no other text."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Using mini for cost efficiency
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,  # Lower temperature for more consistent results
            max_tokens=200,
        )
        
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
        
        logger.debug(f"Generated eBay query: '{enhanced_query}' with exclusions: {exclusion_keywords}")
        
        return (enhanced_query, exclusion_keywords)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI response as JSON: {e}")
        logger.debug(f"Response content: {content}")
        return None
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        return None
