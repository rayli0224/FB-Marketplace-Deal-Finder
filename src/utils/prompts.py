"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."

def get_pre_filtering_prompt(fb_listing_text: str) -> str:
  return f"""You will be given a Facebook Marketplace listing. Determine whether the listing contains enough information to generate a useful eBay search that will find a comparable product for a rational buyer. The listing should not be too vague and should contain enough detail to identify the product and its attributes. 

{fb_listing_text}

Output Format:
{{
  "rejected": true,
  "reason": "brief explanation"
}}

# Examples
## Example 1:

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

## Example 2:

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

## Example 3:

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

def get_query_generation_prompt(fb_listing_text: str) -> str:
    return f"""
You are an expert at generating highly effective eBay Browse API search queries for product comparison.

{fb_listing_text}

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


def get_batch_filtering_prompt(
    fb_listing_text: str,
    ebay_items_text: str,
) -> str:
    """
    Generate the prompt for filtering a batch of eBay items against a FB listing.

    Used for post-filtering in groups of 5. Output is a JSON array, one object per eBay item.
    """
    return f"""You are determining whether multiple eBay items are truly comparable to a single Facebook Marketplace (FB) listing for accurate price comparison.

Your job is NOT to find similar items.
Your job is to decide, for each eBay item, whether it represents the same economic product as the FB listing.

If there is any meaningful doubt for an item, you must reject it.

---

Facebook listing:

{fb_listing_text}

eBay items (compare each individually):

{ebay_items_text}

---

## Core Principle (Most Important Rule)

Each eBay item is comparable ONLY if:
A rational buyer would consider the FB listing and eBay item interchangeable for pricing.

If they would reasonably pay different prices → reject.

Prefer false negatives over false positives.

---

## Step 1 — Extract Price-Defining Attributes (from FB only)

From the Facebook listing, identify ONLY attributes that materially affect price.

Examples:
- Electronics: brand, model, generation, size, storage, key specs.
- Clothing/shoes: brand, model/line, condition.
- Furniture/other: brand, model, material, dimensions (if relevant).

Do NOT invent attributes.
If an attribute is not stated or implied in the FB listing, treat it as unknown.

---

## Step 2 — Compare eBay Items to Those Attributes

For each eBay item:

- If the FB listing specifies a price-defining attribute → it MUST match.
- If the FB listing is vague → use overall semantic similarity.
- If information is missing or unclear → reject.

---

## Hard Rejection Rules (Automatic Reject)

Reject an eBay item if ANY of the following is true:

1. Different Core Product (brand, model, line, generation)
2. Different Functional Variant (locked/unlocked, mini/pro/max, wrong generation/year, storage tier differences)
3. Different Condition Class (new, used, refurbished, broken)
4. Not a Full Product (accessories, parts, services, bundles)
5. Size Rules (Clothing/shoes: size differences allowed; Electronics/furniture: size differences NOT allowed)
6. Missing Critical Information (key attribute cannot be verified)

---

## Allowed Differences (Do NOT Reject For These)

- Color
- Cosmetic wear
- Missing minor accessories (charger, cable, box)
- Clothing/shoe size differences

These differences must NOT change the fundamental product class.

---

## Decision Rule

Accept ONLY if:
All price-defining attributes match
AND no hard rejection rule is triggered
AND there is no meaningful ambiguity.

Otherwise → reject.

---

## Output Format (MANDATORY)

Return a **JSON array** of objects, in the same order as the eBay items, one object per item:

[
  {{
    "rejected": false,
    "reason": "Exact model and specs (2019, 16 inch, i9)"
  }},
  {{
    "rejected": true,
    "reason": "Different generation (2020 vs 2019)"
  }}
]

Rules:
- rejected: true = reject, false = accept.
- reason: ≤ 10 words.
- Include exact distinguishing details in parentheses when applicable.
- No extra text. No markdown. Only valid JSON.
"""

