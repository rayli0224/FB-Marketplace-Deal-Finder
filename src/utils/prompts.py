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
2. Generate an **effective eBay search query** suitable for the Browse API.
3. **ALWAYS provide Browse API parameters** to improve search quality. Include:
   - `filter`: Use ONLY "conditionIds:{{1000}}" for New or "conditionIds:{{3000}}" for Used (no other condition IDs allowed). If the listing is ambiguous, include both "conditionIds:{{1000|3000}}"
   - `marketplace`: Use "EBAY_US" unless location indicates otherwise
   - `sort`: Use "bestMatch" for most searches

Guidelines:

### Query Construction
- Include **brand, model, and product type**.
- Include **generation / year / variant** only if it strongly differentiates the product.
- **Exclude** color, cosmetic descriptors, minor accessories, bundle/lot details.
- Avoid condition terms (used, new, broken) in the query—they can be applied as a filter.
- Queries should be **short**, ideally 1-5 core terms.

### Examples
- Title: "My Stupidity is Your Gain! Sherwin Williams Paint 2 gals"  
  Description: "2 gals of Sun Bleached Ochre Super Paint and Primer in one. One gal was opened to try on the wall as pictured. The other gal has not been opened. I paid $76.99 a gallon. You get 2 gallons for less than the price of one because I made a mistake in color!"  
  → eBay Query: "Sherwin Williams Super Paint and Primer 2 gallon"

- Title: "MacBook Pro 2019 16 inch i9 32GB RAM cracked corner"  
  Description: "Works perfectly just cosmetic damage."  
  → eBay Query: "MacBook Pro 2019 16 inch"

- Title: "Beautiful solid wood farmhouse dining table set"  
  Description: "Real oak, seats 6, includes 4 chairs."  
  → eBay Query: "solid wood dining table"

- Title: "DeWalt 20V Max XR Brushless Drill w battery"  
  Description: "Model DCD791, barely used."  
  → eBay Query: "DeWalt 20V Max XR DCD791"

- Title: "Nike Air Jordan 1 Retro High OG size 10 red"  
  Description: "Worn twice, great condition."  
  → eBay Query: "Air Jordan 1 Retro High OG"


### Browse API Parameter Guidelines
- **Filter:** ONLY use `conditionIds:{{1000}}` for New or `conditionIds:{{3000}}` for Used. No other condition IDs allowed. If the listing is ambiguous, include both "conditionIds:{{1000|3000}}"
- **Marketplace:** Always include. Use "EBAY_US" unless location indicates otherwise.
- **Sort:** Always include. Use "bestMatch" for most searches.

### Output Format
Return ONLY a JSON object exactly like this:

{{
  "enhanced_query": "optimized eBay search query",
  "browse_api_parameters": {{
      "filter": "conditionIds:{{1000|3000}}",
      "marketplace": "EBAY_US",
      "sort": "bestMatch"
  }}
}}
"""


def get_result_filtering_prompt(listing_title: str, listing_price: float, description_text: str, ebay_items_text: str, num_items: int) -> str:
    """
    Generate the prompt for filtering eBay results to match a FB listing.
    
    Args:
        listing_title: Facebook Marketplace listing title
        listing_price: Listing price
        description_text: Listing description (or "No description provided")
        ebay_items_text: Formatted string of eBay items (numbered list with titles and prices)
        num_items: Exact number of eBay items in the list
    
    Returns:
        Formatted prompt string
    """
    
    return f"""You are helping filter eBay search results to find items that are truly comparable to a Facebook Marketplace listing.

Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Description: "{description_text}"

eBay search results ({num_items} items total):
{ebay_items_text}

Note: Each eBay item includes its title, price, condition (if available), and description (if available). Use all available information to make accurate comparability decisions.

Your task: Identify which eBay items are actually comparable to the FB listing. Internally, reason carefully about each item one by one and provide a short justification for each item's accept/reject decision. 

Search on the web for specific product names as needed in order to inform your decision. Do NOT use images or other visual information to make your decision.

An eBay item is comparable if and only if:

1. Core Product Match  
- It refers to the **same core product/model** (same brand, product line, generation, or series).
- If the FB listing is **specific** (contains clear identifying tokens such as brand, model, generation, size, capacity, etc.), then:
  - Those key tokens must also appear in the eBay title, description, or item aspects.
  - Use the detailed description and condition information when available to make more accurate comparisons.
  - If they do not, exclude the item.
- If the FB listing is **vague or generic**, use best judgment based on overall similarity, leveraging description details when available.

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
  - wrong generation
- Minor differences are acceptable only if the core product is clearly the same.
  - color (red vs blue vs unspecified color of the same product)
  - cosmetic wear (scratches, dents, etc.)

5. Size Differences
- Different sizes are acceptable for clothing items because it doesn't affect price. For example, a size 10 Arc'teryx jacket is comparable to a size 12 Arc'teryx jacket.
- For other items such as electronics, different sizes are not acceptable. For example, a 13 inch MacBook Pro is not comparable to a 16 inch MacBook Pro due to large price difference.

Be **strict**. If there is ambiguity, too much missing key information, or reasonable doubt, exclude the item.

Justification must be concise and include the key factors that led to the decision. If relevant, add the exact distinction made between the FB listing and the eBay item in parentheses.

### Examples
- FB Title: "Canon EOS Rebel T7 DSLR camera kit"
  FB Description: "Includes camera body and 18-55mm lens. Used once."
  eBay Results:
    1. "Canon EOS Rebel T7 DSLR with 18-55mm lens bundle" → Accept: "Same model and full kit (18-55mm lens)"
    2. "Canon EOS Rebel T6 camera body only" → Reject: "Different model (T6 vs T7)"
    3. "Canon 50mm f/1.8 lens for Canon DSLR" → Reject: "Accessory (lens) is not full camera"
    4. "Canon EOS Rebel T7 DSLR used, for parts" → Reject: "For parts / not working"
    5. "Canon EOS Rebel T7 DSLR with extra battery" → Accept: "Same model, full product, minor accessory included (battery)"

- FB Title: "MacBook Pro 2019 16 inch i9 32GB RAM"
  FB Description: "Excellent condition, comes with charger."
  eBay Results:
    1. "MacBook Pro 2019 16 inch i9 32GB RAM" → Accept: "Exact model and specs"
    2. "MacBook Pro 2020 16 inch i9" → Reject: "Different generation (2020 vs 2019)"
    3. "MacBook Pro 2019 13 inch i7" → Reject: "Different size and CPU (13 inch vs 16 inch)"
    4. "MacBook Pro 2019 16 inch i9 missing charger" → Accept: "Core product matches, minor missing accessory (charger)"
    5. "MacBook Air 2019 13 inch i5" → Reject: "Different model entirely (MacBook Air vs MacBook Pro)"

- FB Title: "Nike Air Jordan 1 Retro High OG size 10"
  FB Description: "Worn twice, excellent condition."
  eBay Results:
    1. "Air Jordan 1 Retro High OG size 10 black" → Accept: "Core model matches, color irrelevant (black vs unknown)"
    2. "Air Jordan 1 Mid OG size 10" → Reject: "Different variant (Mid vs High)"
    3. "Air Jordan 1 Retro High OG size 9" → Accept: "Size class is irrelevant (9 vs 10)"
    4. "Air Jordan 1 Retro High OG size 10 red, new" → Accept: "Same model (Air Jordan 1 Retro High OG) and size (10)"
    5. "Air Jordan 1 Low OG size 10" → Reject: "Different variant (Low vs High)"

Return your response as a JSON object with exactly this structure:
{{
  "comparable_indices": [1, 3],
  "reasons": {{
    "1": "Same model (Air Jordan 1 Retro High OG) and size (10) and condition",
    "2": "Different product variant (Mid vs High)",
    "3": "Matches core product (Air Jordan 1 Retro High OG)",
    "4": "Accessory (lens) is not full camera"
  }}
}}

Where:
- comparable_indices are 1-based indices from the eBay results list of the items that are suitable for accurate price comparison.  
- reasons is an object mapping each 1-based index to a brief reason explaining why it was accepted or rejected

**CRITICAL REQUIREMENTS - READ CAREFULLY**:
1. There are exactly {num_items} items in the list above (numbered 1 through {num_items}). You MUST provide a reason for EVERY single item. Do not skip any items.
2. The reasons object must contain exactly {num_items} entries, one for each item index from 1 to {num_items}. Every single item must have a reason, no exceptions.
3. Keep each reason BRIEF - one sentence maximum, ideally 5-15 words. Focus only on the key distinguishing factor (e.g., "Different model (T6 vs T7)", "Same product, different size", "Accessory only"). Brevity is critical to ensure you can complete all {num_items} reasons.
4. Process items sequentially from 1 to {num_items} and ensure you complete the entire list before finishing your response.
5. Before finishing, verify that your reasons object contains exactly {num_items} entries (one for each index from 1 to {num_items}). If you find you're missing any, add them before responding.
6. Ensure all JSON strings are properly escaped. If a reason contains quotes, parentheses, or special characters, they must be properly escaped (e.g., use \\" for quotes inside strings). All strings must be properly closed with closing quotes.

Return only the JSON object and no other text."""
