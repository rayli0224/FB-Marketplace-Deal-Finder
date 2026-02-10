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
    
    return f"""You are filtering eBay search results to find items that are truly comparable to a Facebook Marketplace (FB) listing, for accurate price comparison.

### Input

Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Description: "{description_text}"

eBay search results ({num_items} total):
{ebay_items_text}

Each eBay item includes title, price, condition (if available), and description (if available).

---

## How to Think (Internal Process)

Follow these exact steps:

Step 1 — Identify price-defining features of the FB item.  
Extract the minimal set of key attributes that primarily determine price.
Examples:
- Electronics: brand, model, generation, size, storage/specs.
- Clothing/shoes: brand, model/line, condition (size is irrelevant).
- Furniture/other: brand, model, material, dimensions if relevant.

Only use attributes that are actually present in the FB listing.
Ignore cosmetic attributes (color, minor wear) unless they materially affect value.

Step 2 — Compare each eBay item against those features.  
For each item:
- If a key attribute is known in the FB listing, it must match.
- If a key attribute is missing or vague in the FB listing, use best judgment from overall similarity.
- Check condition similarity.
- Check that it is a full product, not a part/accessory/bundle.
- Check for material variants that change price.

Step 3 — Decide strictly.  
If there is ambiguity, missing critical info, or reasonable doubt → reject.

---

## Comparability Rules

An eBay item is comparable if and only if:

1. Core Product Match (Conditional)
- If the FB listing is specific:
  - The same brand/model/line/generation must appear.
- If the FB listing is vague or generic:
  - Use overall semantic similarity and description details.
  - Accept broader matches only when unavoidable.

2. Condition Match
- Similar condition (new vs used vs working).
- Exclude: for parts, broken, not working.

3. Full Product Only
- Exclude accessories, parts, services, bundles, lots.

4. Material Variants
- Exclude variants that affect price:
  - locked vs unlocked
  - mini vs pro vs max
  - wrong generation
- Allow minor variants:
  - color
  - cosmetic wear
  - missing minor accessories (charger, cable)

5. Size Rules
- Clothing/shoes: size differences are OK.
- Electronics/furniture: size differences are NOT OK.

Be strict. Prefer false negatives over false positives.

---

## Output Format (MANDATORY)

Return a JSON object:

{{
  "comparable_indices": [1, 3],
  "reasons": {{
    "1": "Same model and specs",
    "2": "Different generation (2020 vs 2019)",
    "3": "Core product matches",
    "4": "Accessory only"
  }}
}}

### Requirements
1. There are exactly {num_items} eBay items (1 to {num_items}).
2. You MUST give a reason for every single item.
3. Each reason: one sentence, 5–15 words max.
4. Reasons must include exact distinguishing details in parentheses when applicable.
   (e.g., "Different size (13 in vs 16 in) and CPU (i7 vs i9)")
5. Reasons must focus only on the key distinguishing factor.
6. The reasons object must contain exactly {num_items} entries.
7. Return only valid JSON, no extra text.

---

## Compact Examples

Example 1 — Vague FB listing  
FB: "Gaming laptop"  
eBay:
1. "Dell G15 gaming laptop RTX 3060" → Accept: Matches general category and use
2. "Gaming laptop charger" → Reject: Accessory only (charger, not laptop)
3. "Alienware desktop PC" → Reject: Different product category (desktop vs laptop)

Example 2 — Specific FB listing  
FB: "MacBook Pro 2019 16 inch i9 32GB"  
eBay:
1. "MacBook Pro 2019 16 inch i9 32GB" → Accept: Exact model and specs
2. "MacBook Pro 2020 16 inch i9" → Reject: Different generation (2020 vs 2019)
3. "MacBook Pro 2019 13 inch i7" → Reject: Different size (13 in vs 16 in) and CPU (i7 vs i9)
4. "MacBook Pro 2019 16 inch missing charger" → Accept: Core product matches (charger missing)

Example 3 — Clothing  
FB: "Air Jordan 1 Retro High OG size 10"  
eBay:
1. "AJ1 Retro High OG size 9" → Accept: Size irrelevant (9 vs 10)
2. "AJ1 Mid OG size 10" → Reject: Different variant (Mid vs High)
3. "AJ1 Low OG size 10" → Reject: Different variant (Low vs High)

Example 4 — Camera  
FB: "Canon EOS Rebel T7 with 18–55mm lens"  
eBay:
1. "Canon EOS Rebel T7 with kit lens" → Accept: Same full kit (18–55mm lens)
2. "Canon EOS Rebel T6 body only" → Reject: Different model (T6 vs T7)
3. "Canon 50mm f/1.8 lens" → Reject: Accessory only (lens, no camera)
4. "Canon EOS Rebel T7 for parts" → Reject: Not working (for parts)
"""
