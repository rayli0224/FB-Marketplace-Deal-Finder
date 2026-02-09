"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."


def get_query_generation_prompt(listing_title: str, listing_price: float, listing_location: str, description_text: str) -> str:
  
    return f"""
You are an expert at generating highly effective eBay Browse API search queries for product comparison.

Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Location: {listing_location}
- Description: "{description_text}"

Your task:
1. Extract the **core product attributes** that matter for comparison: brand, model, product type, generation, storage/capacity if relevant.
2. Generate a **high-recall eBay search query** suitable for the Browse API.
3. Provide **HARD exclusion keywords** to filter out clearly irrelevant listings.
4. **ALWAYS provide Browse API parameters** to improve search quality. Include:
   - `filter`: Use ONLY "conditionIds:{{1000}}" for New or "conditionIds:{{3000}}" for Used (no other condition IDs allowed). If the listing is ambiguous, include both "conditionsIds:{{1000|3000}}
   - `marketplace`: Use "EBAY_US" unless location indicates otherwise
   - `sort`: Use "bestMatch" for most searches
   - `limit`: Use 50 for good statistical coverage

Guidelines:

### Query Construction (High Recall)
- Include **brand, model, and product type**.
- Include **generation / year / variant** only if it strongly differentiates the product.
- **Exclude** color, cosmetic descriptors, minor accessories, bundle/lot details.
- Avoid condition terms (used, new, broken) in the query—they can be applied as a filter.
- Queries should be **short and broad**, ideally 1–3 core terms.
- Include common alternative spellings or abbreviations if relevant.

### Exclusion Keywords (HARD)
- for parts
- broken
- not working
- empty box
- manual
- packaging
- lot
- bundle

### Examples
- "Nintendo DS Lite Pink" → "Nintendo DS Lite"
- "iPhone 13 Pro 256GB cracked screen" → "iPhone 13 Pro"
- "MacBook Pro 2019 16 inch i9" → "MacBook Pro 2019"
- "Keychron K7 Wireless Mechanical Keyboard" → "Keychron K7"

### Browse API Parameter Guidelines
- **Filter:** ONLY use `conditionIds:{{1000}}` for New or `conditionIds:{{3000}}` for Used. No other condition IDs allowed. If the listing is ambiguous, include both "conditionsIds:{{1000|3000}}.
- **Marketplace:** Always include. Use "EBAY_US" unless location indicates otherwise.
- **Sort:** Always include. Use "bestMatch" for most searches.
- **Limit:** Always include. Use 50 for good statistical coverage.

### Output Format
Return ONLY a JSON object exactly like this:

{{
  "enhanced_query": "optimized eBay search query",
  "exclusion_keywords": ["keyword1", "keyword2", "keyword3"],
  "browse_api_parameters": {{
      "filter": "conditionIds:{{1000|3000}}",
      "marketplace": "EBAY_US",
      "sort": "bestMatch",
      "limit": 50
  }}
}}
"""


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
