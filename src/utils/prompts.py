"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

# System message for pre-filtering (determining if listing has enough info)
PRE_FILTERING_SYSTEM_MESSAGE = "You are an expert at evaluating marketplace listings. Always respond with valid JSON only."

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."

def get_pre_filtering_prompt(fb_listing_text: str) -> str:
  return f"""You will be given a Facebook Marketplace listing. Determine whether the listing contains enough information to generate a useful eBay search that will find a comparable product for a rational buyer. The listing should not be too vague and should contain enough detail to identify the product and its attributes. 

### Facebook Marketplace Listing:
{fb_listing_text}

### Output Format
Return ONLY a JSON object:
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
    return f"""You are comparing multiple eBay items to a single Facebook Marketplace (FB) listing to determine if each item is truly comparable for pricing.

**Important:** Do NOT find similar items. Decide only if the eBay item is the same economic product.  
**Principle:** A rational buyer must consider it interchangeable for pricing. Prefer false negatives over false positives.  

---

Facebook listing:
{fb_listing_text}

eBay items:
{ebay_items_text}

---

### Step 1 — Category
Examples:  
- Electronics: laptop, smartphone, headphones  
- Clothing/Shoes: jacket, shoes, bag  
- Furniture/Home Goods: chair, table, sofa  
- Vehicles: car, motorcycle, bicycle  
- Musical Instruments: guitar, keyboard  
- Collectibles/Toys: LEGO set, board game  
- Books/Media: books, DVDs  
- Miscellaneous: other  

---

### Step 2 — Price-Defining Attributes
Only attributes that materially affect price:  
- Electronics: brand, model, generation/year, specs, size, condition  
- Clothing/Shoes: brand, model/line, material, condition, size  
- Furniture/Home Goods: brand, material, dimensions, condition  
- Vehicles: brand, model, year, mileage, condition, included accessories  
- Musical Instruments: brand, model, type, condition, included accessories  
- Collectibles/Toys: brand, edition, year, completeness, condition  
- Books/Media: title, edition, author, condition  
- Miscellaneous: brand, model, size, material, condition  

Do NOT invent attributes; treat missing as unknown.  

---

### Step 3 — Decision Rules
- **Reject:** Key attribute differs, functional variant differs, extreme condition difference, missing critical components, or critical info missing.  
- **Maybe:** Core product mostly matches, but minor difference exists (missing minor part, small accessory change, slight ambiguity).  
- **Accept:** All key attributes match; minor allowed differences (color, cosmetic wear, size for clothing/shoes).  

---

### Examples
FB: "MacBook Pro 2019 16 inch i9" vs eBay: "MacBook Pro 2020 16 inch i9" → `reject`  
FB: "Leather jacket, size M" vs eBay: "Leather jacket, size L" → `accept`  
FB: "LEGO set, complete" vs eBay: "LEGO set, missing minifigure" → `maybe`  

---

### Output Format
Return JSON array in same order as eBay items:  

[
  {{"decision": "accept", "reason": "Size difference allowed (M vs L)"}},
  {{"decision": "reject", "reason": "Different generation (2020 vs 2019)"}},
  {{"decision": "maybe", "reason": "Missing minor part (minifigure)"}}
]

No extra text. Reason ≤10 words, include key detail.
"""

