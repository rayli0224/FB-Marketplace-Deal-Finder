"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."


def get_query_generation_prompt(original_query: str, listing_title: str, listing_price: float, listing_location: str, description_text: str) -> str:
    """
    Generate the prompt for creating an optimized eBay search query from a FB listing.
    
    Args:
        original_query: The original user search query
        listing_title: Facebook Marketplace listing title
        listing_price: Listing price
        listing_location: Listing location
        description_text: Listing description (or "No description provided")
    
    Returns:
        Formatted prompt string
    """
    return f"""You are helping to find accurate price comparisons on eBay for a Facebook Marketplace listing.

Original user search query: "{original_query}"
Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Location: {listing_location}
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


def get_result_filtering_prompt(listing_title: str, listing_price: float, description_text: str, ebay_items_text: str) -> str:
    """
    Generate the prompt for filtering eBay results to match a FB listing.
    
    Args:
        listing_title: Facebook Marketplace listing title
        listing_price: Listing price
        description_text: Listing description (or "No description provided")
        ebay_items_text: Formatted string of eBay items (numbered list with titles and prices)
    
    Returns:
        Formatted prompt string
    """
    return f"""You are helping filter eBay search results to find items that are truly comparable to a Facebook Marketplace listing.

Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Description: "{description_text}"

eBay search results:
{ebay_items_text}

Your task: Identify which eBay items are actually comparable to the FB listing.

Internally, reason about each item one by one and justify your decision, but do NOT output your reasoning.

An eBay item is comparable if and only if:

1. Core Product Match  
- It refers to the **same core product/model** (same brand, product line, generation, or series).
- If the FB listing is **specific** (contains clear identifying tokens such as brand, model, generation, size, capacity, etc.), then:
  - Those key tokens must also appear in the eBay title or description.
  - If they do not, exclude the item.
- If the FB listing is **vague or generic**, use best judgment based on overall similarity.

2. Condition Match  
- The **condition is similar** (e.g. both new, both used, both working).
- Exclude items marked as:
  - for parts
  - broken / not working
  - damaged in a way that affects functionality

3. Full Product Only  
- It must be a **complete product**, not:
  - an accessory (case, charger, cable, etc.)
  - a part or component
  - a bundle, lot, or multi-item listing
  - a service or subscription

4. Material Variants  
- Exclude items that are a **different variant that materially affects price**, such as:
  - locked vs unlocked
  - mini vs pro vs max
  - wrong size class or generation
- Minor differences (color, storage, cosmetic wear) are acceptable only if the core product is clearly the same.

Be **strict**. If there is ambiguity, missing information, or reasonable doubt, exclude the item.

Return your response as a JSON object with exactly this structure:
{{
  "comparable_indices": [1, 3, 5]
}}

Where comparable_indices are 1-based indices from the eBay results list.

Only include items that are suitable for accurate price comparison.  
Return only the JSON object and no other text."""
