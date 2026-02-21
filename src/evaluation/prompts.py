"""
Prompts for OpenAI API calls in query enhancement and filtering.

Contains prompt templates used for generating eBay search queries and filtering
eBay results to match Facebook Marketplace listings.

Pipeline stages:
  1. Pre-recon filter   — lightweight LLM + rules, gates on raw listing quality
  2. Product recon      — internet search + LLM, identifies and disambiguates product
                          (post-recon gate is embedded in recon output via `computable`)
  3. eBay query gen     — generates eBay sold-listings search query from recon output
  4. Post-eBay filter   — determines if each eBay listing is truly comparable
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scrapers.fb_marketplace_scraper import Listing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 1 — Pre-Recon Filter
# ---------------------------------------------------------------------------

PRE_RECON_FILTER_SYSTEM_MESSAGE = """You are evaluating raw Facebook Marketplace listings to decide whether they are worth investigating further.

Your job is NOT to assess whether the product can be precisely identified — that comes later.
Your job is to reject listings that are so vague, malformed, or inherently unquantifiable that no amount of research could produce a reliable price comparison.

Rules:
- Reject if the listing is a non-inherent lot or bundle (e.g., "box of clothes", "lot of 50 games", "bag of misc tools"). Inherent bundles like "pair of shoes" or "chess set" are fine.
- Reject if the listing is a service, rental, or non-physical item.
- Reject if the listing has no identifiable product — just a vague category with no brand, model, or specific name (e.g., "bag", "blender", "lamp").
- Reject if the listing is clearly from a buyer, not a seller (covered separately by rules, but flag if unsure).
- Accept if there is a brand, model, specific product name, or enough description to narrow down a product universe.

Bias toward false rejects. It is better to skip a listing than to produce a bad price comparison.

Always respond with valid JSON only."""


def get_pre_recon_filter_prompt(fb_listing_text: str) -> str:
    """Pre-recon filter prompt - evaluates raw listing before product recon."""
    return f"""Evaluate this Facebook Marketplace listing. Decide whether it has enough signal to be worth investigating for price comparison.

{fb_listing_text}

### Examples

Facebook Marketplace listing:
- Title: "Ninja smoothie blender"
- Price: $30.00
- Description: "Condition Used - Good Brand Ninja"
Output:
{{"rejected": false, "reason": "Brand and product type sufficient to identify product universe"}}

---

Facebook Marketplace listing:
- Title: "Messenger bag"
- Price: $5.00
- Description: ""
Output:
{{"rejected": true, "reason": "No brand or identifiable product details"}}

---

Facebook Marketplace listing:
- Title: "Lot of 50 assorted Xbox games"
- Price: $40.00
- Description: ""
Output:
{{"rejected": true, "reason": "Non-inherent lot — unit price cannot be reliably estimated"}}

---

Facebook Marketplace listing:
- Title: "Chess set"
- Price: $20.00
- Description: "Wooden, full set"
Output:
{{"rejected": false, "reason": "Inherent set; product type identifiable"}}

---

Facebook Marketplace listing:
- Title: "iPhone 12"
- Price: $200.00
- Description: ""
Output:
{{"rejected": false, "reason": "Specific product name identifiable; variant ambiguity resolved later"}}

### Output Format
Return ONLY a valid JSON object:
{{
  "rejected": true,
  "reason": "brief explanation (1 sentence)"
}}"""


# ---------------------------------------------------------------------------
# Step 2 — Product Recon
# ---------------------------------------------------------------------------

PRODUCT_RECON_SYSTEM_MESSAGE = """You are identifying and disambiguating the real-world product described in a Facebook Marketplace listing.

Your goal is to DISAMBIGUATE, not to guess. Use internet search to resolve naming ambiguity, identify the correct product, and determine which attributes materially affect its market price.

Rules:
- Do NOT invent details. Only include information that is explicit in the listing or verifiable via search.
- If multiple plausible products exist and they have meaningfully different price points, mark the conflicting fields as "unknown".
- If multiple plausible products exist but their price difference is negligible, pick the most likely and note the ambiguity in `notes`.
- Mark `computable` as false if any high-price-impact attribute is unknown, or if the product cannot be reliably disambiguated.
- Condition of products can typically all be assumed to be used with regular wear and tear, as long as it's not listed "for parts" or "not working".
- When in doubt, assign medium rather than high. Reserve high for attributes that cause unambiguous, well-known price splits (e.g., iPhone storage tiers, electric vs acoustic instruments).

Always respond with valid JSON only."""


def get_internet_product_recon_prompt(fb_listing_text: str) -> str:
    return f"""Identify the real-world product in this Facebook Marketplace listing. Search the internet to resolve ambiguity and determine price-relevant attributes.

{fb_listing_text}

### Output Format
Return a single JSON object:

{{
  "canonical_name": "full product name as commonly known",
  "brand": "brand name | unknown",
  "category": "e.g. Electronics > Smartphones",
  "model_or_series": "specific model or series | unknown",
  "year_or_generation": "year or generation | unknown",
  "key_attributes": [
    {{"attribute": "storage", "value": "128GB", "price_impact": "high"}},
    {{"attribute": "color", "value": "black", "price_impact": "low"}}
  ],
  "computable": true,
  "reject_reason": "null if computable, otherwise brief explanation",
  "notes": "max 1 sentence on any remaining ambiguity, or empty string"
}}

### Field guidelines
- `key_attributes`: list only attributes that exist for this product. `price_impact` must be "high", "medium", or "low". This is not general importance. It is based on the impact on the realistic resale price of the product.
- `computable`: set to false if any high-price-impact attribute is unknown, or if the product cannot be confidently identified. Differences in low to medium price-impact attributes are acceptable.
- `reject_reason`: required if `computable` is false, otherwise null.
- `notes`: flag any ambiguity that could affect pricing even if `computable` is true.


### Examples

#### Example 1:
Trek Marlin 5 29" mountain bike (no year specified):
- model: known and specific, anchors price range well
- year: medium — Marlin 5 resale prices vary ~15–20% across generations
- frame_size: low — resale prices are nearly identical across frame sizes
- condition: low — like new vs fair makes a small difference
→ computable: true — only one medium-impact attribute unknown (year); model anchors the range

#### Example 2:
iPhone 13 Pro (no storage specified):
- storage: high — 128GB vs 512GB is a >40% price difference
→ computable: false — storage is unknown and high-impact

#### Example 3:
London Fog jacket (no style, size, material, or condition specified):
- style/line: medium — trench coat vs windbreaker vs wool overcoat span a wide range
- size: medium — some size premium exists
- material: medium — wool vs synthetic meaningfully affects price
- condition: low — slight difference in price for outerwear
→ computable: false — multiple medium-impact attributes unknown simultaneously; brand + generic type insufficient to anchor price range

#### Example 4:
PSA 10 Charizard 25th Anniversary Celebrations pokemon card (graded slab):
- card: known and specific
- grade: PSA 10 stated in listing
- set: 25th Anniversary Celebrations stated
- condition: high — condition for collectibles is very important, and the grade is stated in the listing
→ computable: true
"""


# ---------------------------------------------------------------------------
# Step 3 — eBay Query Generation
# ---------------------------------------------------------------------------

QUERY_GENERATION_SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."


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


# ---------------------------------------------------------------------------
# Step 4 — Post-eBay Filter
# ---------------------------------------------------------------------------

RESULT_FILTERING_SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."


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

### Step 3 — Quantity/Lot Matching
Compare the quantity or lot size between the Facebook listing and the eBay item. Reject items with different quantities:
- **Reject:** FB listing is a single item but eBay item is a lot/bundle/multi-pack, OR FB listing is a set/bundle but eBay item is a single item.
- **Accept:** Quantities match (both single items, both same-size sets, or quantity is unclear/not applicable).

Examples:
- FB: "single battery" vs eBay: "4-pack of batteries" → `reject` (quantity mismatch)
- FB: "MacBook i9 Pro" vs eBay: "MacBook Pro 16in 32GB RAM" → check other attributes (both single items)
- FB: "10 game series" vs eBay: "full game series (10)" → check other attributes (quantities match)

---

### Step 4 — Decision Rules
- **Reject:** Key attribute differs, functional variant differs, extreme condition difference, missing critical components, critical info missing, OR quantity/lot mismatch (from Step 3).  
- **Maybe:** Core product mostly matches, but minor difference exists (missing minor part, small accessory change, slight ambiguity).  
- **Accept:** All key attributes match; minor allowed differences (color, cosmetic wear, size for clothing/shoes).  

---

### Examples
FB: "MacBook Pro 2019 16 inch i9" vs eBay: "MacBook Pro 2020 16 inch i9" → `reject`  
FB: "Leather jacket, size M" vs eBay: "Leather jacket, size L" → `accept`  
FB: "LEGO set, complete" vs eBay: "LEGO set, missing minifigure" → `maybe`  
FB: "single battery" vs eBay: "4-pack batteries" → `reject` (quantity mismatch)  

---

### Output Format
Return JSON array in same order as eBay items:  

[
  {{"decision": "accept", "reason": "Size difference allowed (M vs L)"}},
  {{"decision": "reject", "reason": "Different generation (2020 vs 2019)"}},
  {{"decision": "reject", "reason": "Quantity mismatch (single vs 4-pack)"}},
  {{"decision": "maybe", "reason": "Missing minor part (minifigure)"}}
]

No extra text. Reason ≤10 words, include key detail.
"""