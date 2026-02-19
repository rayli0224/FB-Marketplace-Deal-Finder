"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scrapers.fb_marketplace_scraper import Listing


def format_fb_listing_for_prompt(listing: "Listing") -> str:
    """
    Format a FB listing as text for prompts.
    Includes title, price, location (if available), and description (if available).
    """
    listing_text = f"Facebook Marketplace listing:\n- Title: {listing.title}\n- Price: ${listing.price:.2f}"
    if listing.location:
        listing_text += f"\n- Location: {listing.location}"
    if listing.description:
        listing_text += f"\n- Description: {listing.description}"
    return listing_text

# System message for pre-filtering (determining if listing has enough info)
PRE_FILTERING_SYSTEM_MESSAGE = "You are an expert at evaluating marketplace listings. Always respond with valid JSON only."

# System message for query generation
QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."

# System message for internet product recon
PRODUCT_RECON_SYSTEM_MESSAGE = "You are an expert at identifying real-world products from marketplace listings. Always respond with valid JSON only."

# System message for result filtering
RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."

def get_pre_filtering_prompt(fb_listing_text: str, product_recon_json: str = "") -> str:
  return f"""You will be given a Facebook Marketplace listing. Determine whether the listing contains enough information to generate a useful eBay search that will find a reasonably comparable product for pricing.

The goal is not perfect identification. The goal is whether we can estimate fair market value with reasonable confidence. Depending on the product, differences between variants can be big or small (e.g., collectors items, electronics, book series).

Ambiguity is acceptable if price differences between likely variants are typically small. Reject only if the listing is too vague to form a representative eBay search.

Prefer false accepts over false rejects.

### Facebook Marketplace Listing:
{fb_listing_text}

### Product Details from Internet Search:
{product_recon_json}

### Output Format
Return ONLY a valid JSON object with this exact format:
{{
  "rejected": true,
  "reason": "brief explanation"
}}

# Examples

## Example 1:

Facebook Marketplace listing:
- Title: "Phantasy Star Online 3 GameCube"
- Price: $40.00
- Description: ""

Output:
{{
  "rejected": false,
  "reason": "Game title and platform sufficient for representative pricing despite minor version ambiguity"
}}

## Example 2:

Facebook Marketplace listing:
- Title: "50 Xbox One & Xbox 360 Games - job lot"
- Price: £30.00
- Description: ""

Output:
{{
  "rejected": false,
  "reason": "Quantity and console specified; sufficient for lot pricing"
}}

## Example 3:

Facebook Marketplace listing:
- Title: "Messenger bag"
- Price: $5.00
- Description: ""

Output:
{{
  "rejected": true,
  "reason": "No brand or identifiable product details"
}}

## Example 4:

Facebook Marketplace listing:
- Title: "Ninja smoothie blender"
- Price: $30.00
- Description: "Condition Used - Good Brand Ninja"

Output:
{{
  "rejected": false,
  "reason": "Brand and product type sufficient for pricing"
}}
"""


def get_query_generation_prompt(product_recon_json: str) -> str:
    return f"""
You are an expert at generating highly effective eBay search queries for product comparison.

You are given a structured product intelligence object that already identifies and disambiguates the real-world product.

## Product details from internet search:
{product_recon_json}

Your task:
1. Extract the **core product attributes** that matter for comparison: brand, model, product type, generation, storage/capacity if relevant.
2. Generate an **effective eBay search query** that will find comparable sold listings.

Rules:
- Use ONLY information present in the product intelligence.
- Do NOT invent or assume missing details.
- If a field is "unknown", do not include it in the query.
- Prefer broader queries over overly specific ones when uncertain.

Guidelines:

### Query Construction
- Include **brand, model, and product type** when available.
- Include **generation / year / variant** only if it strongly differentiates the product.
- **Exclude** color, cosmetic descriptors, minor accessories, bundle/lot details.
- Avoid condition terms (used, new, broken) in the query.
- Queries should be **short**, ideally 1–5 core terms.

### Examples
- Title: "My Stupidity is Your Gain! Sherwin Williams Paint 2 gals"  
  Description: "2 gals of Sun Bleached Ochre Super Paint and Primer in one..."  
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

### Output Format
Return ONLY a JSON object:
{{
  "enhanced_query": "optimized eBay search query"
}}
"""



def get_batch_filtering_prompt(
    product_recon_json: str,
    ebay_items_text: str,
) -> str:
    """
    Generate the prompt for filtering a batch of eBay items against a grounded product.

    Used for post-filtering in groups of 5. Output is a JSON array, one object per eBay item.
    """
    return f"""You are comparing multiple eBay items to a single real-world product to determine if each item is truly comparable for pricing.

You are given a structured product intelligence object that already disambiguates the Facebook Marketplace listing.

**Important:** Do NOT find similar items. Decide only if the eBay item is the same economic product.  
**Principle:** A rational buyer must consider it interchangeable for pricing. Prefer false negatives over false positives.  

---

## Product details from internet search:
{product_recon_json}

## eBay items:
{ebay_items_text}

---

### Step 1 — Category
Use the category from the product intelligence. Examples:  
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
Use the product intelligence to determine which attributes matter. Only attributes that materially affect price:  
- Electronics: brand, model, generation/year, specs, size, condition  
- Clothing/Shoes: brand, model/line, material, condition, size  
- Furniture/Home Goods: brand, material, dimensions, condition  
- Vehicles: brand, model, year, mileage, condition, included accessories  
- Musical Instruments: brand, model, type, condition, included accessories  
- Collectibles/Toys: brand, edition, year, completeness, condition  
- Books/Media: title, edition, author, condition  
- Miscellaneous: brand, model, size, material, condition  

Do NOT invent attributes. Treat fields marked as "unknown" as unknown.
For electronics, OEM stands for Original Equipment Manufacturer, and it is typically comparable to the original brand.

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


def get_internet_product_recon_prompt(fb_listing_text: str) -> str:
    return f"""
You are identifying the real-world product described in a Facebook Marketplace listing.

Your goal is to DISAMBIGUATE, not to guess.
Make an internet search to gather more information, resolve naming ambiguity, and identify the product universe.
Identify the most precise product possible. If ambiguity remains, assess whether the unresolved differences would meaningfully impact market price. 

Rules:
- Do NOT invent details.
- If multiple plausible products exist, mark fields as "unknown".
- Only add information that is explicit in the listing or objectively verifiable without guessing.

Return a single JSON object with:

{{
  "canonical_name": "...",
  "brand": "...",
  "category": "...",
  "model_or_series": "... | unknown",
  "year_or_generation": "... | unknown",
  "variant_dimensions": ["..."],
  "notes": "max 1 sentence or empty"
}}

Field guidelines:
- model_or_series / year_or_generation: use "unknown" if not certain.
- variant_dimensions: features that impact price (e.g., storage tier, sealed vs opened).
- notes: anything to note or eliminate price ambiguity.

Facebook listing:
{fb_listing_text}
"""