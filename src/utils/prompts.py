"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."

def get_pre_filtering_prompt(listing_title: str, listing_price: float, listing_location: str, description_text: str) -> str:
  return f"""You will be given a Facebook Marketplace listing. If the listing lacks enough information to generate a comprehensive, useful eBay search (e.g. the listing is too vague, generic, or essentially empty), you may reject by returning a JSON object with "rejected": true and "reason": "brief explanation" instead of generating a query.

Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Location: {listing_location}
- Description: "{description_text}"

Output Format:
{{
  "rejected": true,
  "reason": "brief explanation"
}}

Example 1:

Facebook Marketplace listing:
- Title: "Nuphy Air 75 V2"
- Price: $70.00
- Location: San Jose, CA
- Description: ""

Output:
{{
  "rejected": false,
  "reason": "Listing contains enough details about the exact product name and model"
}}

Example 2:

Facebook Marketplace listing:
- Title: "Messenger bag"
- Price: $5.00
- Location: San Jose, CA
- Description: ""

Output:
{{
  "rejected": true,
  "reason": "Listing doesn't contain any brand, product, or model details"
}}

Example 3:

Facebook Marketplace listing:
- Title: "Ninja smoothie blender"
- Price: $30.00
- Location: Los Gatos, CA
- Description: "Condition Used - Good Brand Ninja Pick up in Los Gator or San Jose downtown"

Output:
{{
  "rejected": true,
  "reason": "Listing contains brand name, but doesn't contain any product details"
}}
"""

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
Return ONLY a JSON object:
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
        description_text: Listing description
        ebay_items_text: Formatted string of eBay items (numbered list with titles and prices)
        num_items: Exact number of eBay items in the list
    
    Returns:
        Formatted prompt string
    """
    
    return f"""You are filtering eBay search results to find items that are truly comparable to a Facebook Marketplace (FB) listing for accurate price comparison. For every single eBay item, you must compare the item to the Facebook listing and decide if the item is comparable enough to be used for price comparison. Each eBay item includes title, price, condition (if available), and description (if available).


Facebook Marketplace listing:
- Title: "{listing_title}"
- Price: ${listing_price:.2f}
- Description: "{description_text}"

eBay items ({num_items} total):
{ebay_items_text}

---

## How to Think (Internal Process)

Follow these exact steps:

Step 1 — Identify price-defining features of the Facebook listing.  
Extract the minimal set of key attributes that primarily determine price.
Examples:
- Electronics: brand, model, generation, size, storage/specs.
- Clothing/shoes: brand, model/line, condition (size is irrelevant).
- Furniture/other: brand, model, material, dimensions if relevant.

Only use attributes that are actually present in the Facebook listing.
Ignore cosmetic attributes (color, minor wear) unless they materially affect value.

Step 2 — Compare each eBay item against those features.  
For each item:
- If a key attribute is known in the Facebook listing, it must match.
- If a key attribute is missing or vague in the Facebook listing, use best judgment from overall similarity.
- Check condition similarity.
- Check that it is a full product, not a part/accessory/bundle.
- Check for material variants that change price.

Step 3 — Decide strictly.  
If there is ambiguity, missing critical info, or reasonable doubt → reject.

---

## Comparability Rules

An eBay item is comparable if and only if:

1. Core Product Match (Conditional)
- If the Facebook listing is specific:
  - The same brand/model/line/generation must appear.
- If the Facebook listing is vague or generic:
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
- Clothing/shoes: size differences are acceptable.
- Electronics/furniture: size differences are not acceptable.

Be strict. Prefer false negatives over false positives.

---

## Output Format (MANDATORY)

Return a JSON object with the following format:

{{
  "results": [
    {{ "id": 1, "rejected": false, "reason": "Same model and specs" }},
    {{ "id": 2, "rejected": true, "reason": "Different generation (2020 vs 2019)" }},
    {{ "id": 3, "rejected": false, "reason": "Core product matches" }},
    {{ "id": 4, "rejected": true, "reason": "Accessory only" }}
  ]
}}

Rules:
- id: 1-based index of the eBay item.
- rejected: true = reject, false = accept.
- reason: a brief explanation of why the item was accepted or rejected.
- The array length MUST exactly match the number of {num_items} eBay items.
- The array order MUST match the eBay items order.
- Each reason must be ≤ 10 words.
- Do NOT include item titles, indices, or any extra fields.
- Return only valid JSON, no extra text.
- Reasons must include exact distinguishing details in parentheses when applicable.
   (e.g., "Different size (13 in vs 16 in) and CPU (i7 vs i9)")

---

### Example 1 — Specific Facebook listing
FB: "MacBook Pro 2019 16 inch i9 32GB"
eBay:
1. "MacBook Pro 2019 16 inch i9 32GB"
2. "MacBook Pro 2020 16 inch i9"
3. "MacBook Pro 2019 13 inch i7"
4. "MacBook Pro 2019 16 inch missing charger"

Output:
{{
  "results": [
    {{ "id": 1, "rejected": false, "reason": "Exact model and specs (2019, 16 inch, i9)" }},
    {{ "id": 2, "rejected": true, "reason": "Different generation (2020 vs 2019)" }},
    {{ "id": 3, "rejected": true, "reason": "Different size and CPU (13 inch, i7)" }},
    {{ "id": 4, "rejected": false, "reason": "Core product matches" }}
  ]
}}

### Example 2 — Clothing
FB: "Air Jordan 1 Retro High OG size 10"
eBay:
1. "AJ1 Retro High OG size 9"
2. "AJ1 Mid OG size 10"
3. "AJ1 Low OG size 10"

Output:
{{
  "results": [
    {{ "id": 1, "rejected": false, "reason": "Same model (size difference acceptable)" }},
    {{ "id": 2, "rejected": true, "reason": "Different variant (Mid vs High)" }},
    {{ "id": 3, "rejected": true, "reason": "Different variant (Low vs High)" }}
  ]
}}

### Example 3 — Camera
FB: "Canon EOS Rebel T7 with 18–55mm lens"
eBay:
1. "Canon EOS Rebel T7 with kit lens"
2. "Canon EOS Rebel T6 body only"
3. "Canon 50mm f/1.8 lens"
4. "Canon EOS Rebel T7 for parts"

Output:
{{
  "results": [
    {{ "id": 1, "rejected": false, "reason": "Same full kit (18–55mm lens)" }},
    {{ "id": 2, "rejected": true, "reason": "Different model (T6 vs T7)" }},
    {{ "id": 3, "rejected": true, "reason": "Accessory only (lens, no camera)" }},
    {{ "id": 4, "rejected": true, "reason": "Not working (for parts)" }}
  ]
}}
"""

