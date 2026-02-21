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
    listing_text = (
        f"Facebook Marketplace listing:\n"
        f"- Title: {listing.title}\n"
        f"- Price: ${listing.price:.2f}"
    )
    if listing.location:
        listing_text += f"\n- Location: {listing.location}"
    if listing.description:
        listing_text += f"\n- Description: {listing.description}"
    return listing_text


# ---------------------------------------------------------------------------
# Stage 1 — Pre-Recon Filter
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

---

### Output Format
Return ONLY a valid JSON object:
{{
  "rejected": true,
  "reason": "brief explanation (1 sentence)"
}}"""

# ---------------------------------------------------------------------------
# Stage 2 — Product Recon
# ---------------------------------------------------------------------------

PRODUCT_RECON_SYSTEM_MESSAGE = """You are identifying and disambiguating the real-world product described in a Facebook Marketplace listing.

Your goal is to DISAMBIGUATE, not to guess. Use internet search to resolve naming ambiguity, identify the correct product, and determine which attributes materially affect its market price.

Rules:
- Do NOT invent details. Only include information that is explicit in the listing or verifiable via search.
- If multiple plausible products exist and they have meaningfully different price points, mark the conflicting fields as "unknown".
- If multiple plausible products exist but their price difference is negligible, pick the most likely and note the ambiguity in `notes`.
- Mark `computable` as false if any high-price-impact attribute is unknown, or if the product cannot be reliably disambiguated.
- Mark `computable` as false if multiple medium-impact attributes are simultaneously unknown and together they would produce high price variance. One unknown medium-impact attribute is acceptable; several compounding unknowns are not.
- Assume all product claims in the listing are authentic and accurate unless the listing itself signals otherwise (e.g., "-style", "-like", "replica", "inspired by", "not official"). Do not reject based on inability to verify claims externally. Verification is not your job — price comparison is.
- Brand + generic product type alone is insufficient if the product type spans a wide price range. Reject if there is no model name, style, line, or other differentiator that narrows the product to a recognizable price range (e.g., "London Fog jacket", "Nike shoes", "Levi's jeans" with no further detail).

When assigning `price_impact`, consider the actual dollar variance the attribute causes within this product's realistic resale price range — not whether the attribute matters in general:
- high: causes >20% price difference within the likely resale range
- medium: causes 10–20% price difference
- low: causes <10% price difference

A specific, recognizable model name often anchors the price range tightly enough that secondary attributes (year, size, color) become medium or low impact. Do not automatically treat unknown secondary attributes as high-impact without considering the actual price variance they cause for this specific product.

Always respond with valid JSON only."""


def get_product_recon_prompt(fb_listing_text: str) -> str:
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
- `key_attributes`: list only attributes that exist for this product. `price_impact` must be "high", "medium", or "low". Base impact on actual resale price variance, not general importance.
- `computable`: set to false if any `price_impact: high` attribute is unknown, if multiple medium-impact attributes are simultaneously unknown, or if the product cannot be confidently identified. Unknown low-impact attributes do not cause rejection.
- `reject_reason`: required if `computable` is false, otherwise null.
- `notes`: flag any ambiguity that could affect pricing even if `computable` is true.

### Examples of price_impact calibration

iPhone 12 (no storage specified):
- storage: high — 64GB sells for ~$150, 256GB for ~$230, a 50%+ difference
- color: low — negligible resale price difference
→ computable: false — storage is unknown and high-impact

Trek Marlin 5 29" mountain bike (no year specified):
- model: known and specific, anchors price range well
- year: medium — Marlin 5 resale prices vary ~15–20% across generations
- frame_size: low — resale prices are nearly identical across frame sizes
- condition: low — like new vs fair makes a small difference
→ computable: true — only one medium-impact attribute unknown (year); model anchors the range

Schwinn Ranger hybrid/mountain bike (no year or size specified):
- model: known; low-end bike with a narrow resale range (~$40–$100)
- year/variant: low — price variance across Ranger variants is small within the overall range
→ computable: true — model name is sufficient to estimate fair market value

iPhone 13 Pro (no storage specified):
- storage: high — 128GB vs 512GB is a >40% price difference
→ computable: false — storage is unknown and high-impact

London Fog jacket (no style, size, material, or condition specified):
- style/line: medium — trench coat vs windbreaker vs wool overcoat span a wide range
- size: medium — some size premium exists
- material: medium — wool vs synthetic meaningfully affects price
- condition: medium — significant price driver for outerwear
→ computable: false — multiple medium-impact attributes unknown simultaneously; brand + generic type insufficient to anchor price range

PSA 10 Charizard 25th Anniversary Celebrations pokemon card (graded slab):
- card: known and specific
- grade: PSA 10 stated in listing — assume accurate
- set: 25th Anniversary Celebrations stated — assume accurate
→ computable: true — listing claims are taken at face value; authenticity verification is not required"""
# Alias for backward compatibility
get_internet_product_recon_prompt = get_product_recon_prompt


# ---------------------------------------------------------------------------
# Stage 3 — eBay Query Generation
# ---------------------------------------------------------------------------

QUERY_GENERATION_SYSTEM_MESSAGE = """You are generating eBay sold-listings search queries from structured product intelligence.

Rules:
- Use ONLY information present in the product intelligence. Do not invent or assume missing details.
- Do not include fields marked as "unknown".
- Do not include color, condition terms, cosmetic descriptors, or minor accessories.
- Prefer broader queries over overly specific ones when uncertain.
- For products inherently sold in multiples (e.g., a pair of shoes, a set of dishes), reflect the quantity in the query.
- Queries should be short — ideally 2–5 core terms.

Always respond with valid JSON only."""


def get_query_generation_prompt(product_recon_json: str) -> str:
    return f"""Generate an eBay sold-listings search query for this product.

## Product intelligence:
{product_recon_json}

### Query construction guidelines
- Always include brand and model when available.
- Include year or generation only if it is a high-price-impact differentiator.
- If model is unknown but canonical name is specific enough, use canonical name.
- Exclude color, condition, cosmetic descriptors, accessories.

### Examples
Product: Sherwin Williams Super Paint and Primer, 2 gallons
→ {{"enhanced_query": "Sherwin Williams Super Paint Primer 2 gallon"}}

Product: MacBook Pro 16-inch 2019, i9, 32GB RAM (cosmetic damage noted)
→ {{"enhanced_query": "MacBook Pro 16 inch 2019 i9"}}

Product: Solid oak dining table, seats 6, includes 4 chairs
→ {{"enhanced_query": "solid wood dining table set"}}

Product: DeWalt 20V Max XR Brushless Drill, model DCD791
→ {{"enhanced_query": "DeWalt DCD791"}}

Product: Air Jordan 1 Retro High OG, size 10, red (pair)
→ {{"enhanced_query": "Air Jordan 1 Retro High OG"}}

### Output Format
Return ONLY a JSON object:
{{
  "enhanced_query": "optimized eBay search query"
}}"""


# ---------------------------------------------------------------------------
# Stage 4 — Post-eBay Filter
# ---------------------------------------------------------------------------

RESULT_FILTERING_SYSTEM_MESSAGE = """You are determining whether eBay sold listings are truly comparable to a specific product for pricing purposes.

Core principle: A rational buyer must consider the eBay item interchangeable with the target product. You are not finding similar items — you are verifying economic equivalence.

Decision definitions:
- accept: all high- and medium-impact attributes match; minor differences allowed (color, cosmetic wear, clothing size)
- maybe: core product matches but there is minor ambiguity, a missing minor accessory, or a low-impact difference
- reject: any high-impact attribute mismatches, quantity/lot mismatch, accessory listed instead of full product, or critical component missing

Bias toward reject. A missed comparison is acceptable; a bad comparison is not.

Condition policy:
- Condition differences are generally acceptable — eBay sold listings naturally span a range of conditions and this averages out.
- Reject if the eBay listing is "for parts / not working" or equivalent.
- Reject if the eBay listing is factory sealed / brand new and the FB listing is clearly used (applies especially to collectibles and electronics where sealed carries a significant premium).
- All other condition grades (good, very good, excellent, lightly used, some wear) are considered comparable.

Key attribute guidance by category:
- Electronics: brand, model, generation/year, specs (storage, RAM, screen size)
- Clothing/Shoes: brand, model/line, material — size differences are acceptable
- Furniture/Home Goods: brand, material, dimensions
- Collectibles/Toys: brand, set name, edition, completeness
- Books/Media: title, edition, author
- Musical Instruments: brand, model, included accessories
- Vehicles: brand, model, year
- Miscellaneous: brand, model, size, material

For electronics, OEM (Original Equipment Manufacturer) parts are generally comparable to original brand parts.

Always respond with valid JSON only."""


def get_batch_filtering_prompt(
    product_recon_json: str,
    ebay_items_text: str,
) -> str:
    """
    Generate the prompt for filtering a batch of eBay items against a grounded product.
    Used for post-filtering in groups of 5. Output is a JSON array, one object per eBay item.
    """
    return f"""Compare each eBay item to the target product and decide if it is economically comparable for pricing.

## Target product intelligence:
{product_recon_json}

## eBay items:
{ebay_items_text}

---

### Instructions

For each eBay item, reason through the following before giving a verdict:

1. **Quantity match**: Does the eBay listing match the quantity of the target product?
   - Reject if FB is a single item and eBay is a lot/bundle/multi-pack, or vice versa.
   - Accept if quantities match or quantity is not applicable.

2. **Key attribute check**: Using the `key_attributes` from the product intelligence, check each attribute against the eBay listing.
   - Focus on attributes with `price_impact: high` or `medium`. Low-impact mismatches (e.g., color) are acceptable.
   - If an attribute is "unknown" in the product intelligence, do not penalize the eBay item for it.
   - Do not penalize for condition differences unless the eBay item is "for parts / not working", or is factory sealed / brand new while the FB listing is clearly used.

3. **Verdict**: Apply the decision definitions from your instructions.

---

### Examples

Target: MacBook Pro 2019 16-inch i9 | eBay: MacBook Pro 2020 16-inch i9
→ {{"key_attributes_checked": {{"model": "match", "year": "mismatch — 2020 vs 2019"}}, "quantity_match": true, "decision": "reject", "reason": "Year mismatch (2020 vs 2019)"}}

Target: Leather jacket size M | eBay: Leather jacket size L
→ {{"key_attributes_checked": {{"brand": "match", "material": "match", "size": "mismatch — M vs L"}}, "quantity_match": true, "decision": "accept", "reason": "Size difference acceptable for clothing pricing"}}

Target: LEGO set, complete | eBay: LEGO set, missing minifigure
→ {{"key_attributes_checked": {{"set": "match", "completeness": "minor difference — missing minifigure"}}, "quantity_match": true, "decision": "maybe", "reason": "Missing minor component (minifigure)"}}

Target: single AA battery | eBay: 4-pack AA batteries
→ {{"key_attributes_checked": {{}}, "quantity_match": false, "decision": "reject", "reason": "Quantity mismatch (single vs 4-pack)"}}

Target: used Sony WH-1000XM4 | eBay: Sony WH-1000XM4 (good condition)
→ {{"key_attributes_checked": {{"model": "match", "condition": "acceptable — both used"}}, "quantity_match": true, "decision": "accept", "reason": "Condition difference within acceptable range"}}

Target: used Pokemon card | eBay: Pokemon card (factory sealed booster)
→ {{"key_attributes_checked": {{"card": "match", "condition": "mismatch — sealed vs used"}}, "quantity_match": true, "decision": "reject", "reason": "Sealed carries significant premium over used"}}

Target: Sony WH-1000XM4 | eBay: Sony WH-1000XM4 (for parts, broken headband)
→ {{"key_attributes_checked": {{"model": "match", "condition": "mismatch — for parts/not working"}}, "quantity_match": true, "decision": "reject", "reason": "For parts listing not comparable"}}

---

### Output Format
Return a JSON array in the same order as the eBay items. One object per item:

[
  {{
    "key_attributes_checked": {{"attribute_name": "match | mismatch — detail"}},
    "quantity_match": true,
    "decision": "accept | maybe | reject",
    "reason": "10 words max, include key detail"
  }}
]

No extra text outside the JSON array."""