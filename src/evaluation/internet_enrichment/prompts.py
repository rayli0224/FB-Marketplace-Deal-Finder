"""Prompts for internet enrichment (product recon step)."""

from src.evaluation.listing_format import format_fb_listing_for_prompt

SYSTEM_MESSAGE = """You are identifying and disambiguating the real-world product described in a Facebook Marketplace listing.

Your goal is to DISAMBIGUATE, not to guess. Use internet search to resolve naming ambiguity, identify the correct product, and determine which attributes materially affect its market price.

Rules:
- Do NOT invent details. Only include information that is explicit in the listing or verifiable via search.
- If multiple plausible products exist and they have meaningfully different price points, mark the conflicting fields as "unknown".
- If multiple plausible products exist but their price difference is negligible, pick the most likely and note the ambiguity in `notes`.
- Mark `computable` as false if any high-price-impact attribute is unknown, or if the product cannot be reliably disambiguated.
- Condition of products can typically all be assumed to be used with regular wear and tear, as long as it's not listed "for parts" or "not working".
- When in doubt, assign medium rather than high. Reserve high for attributes that cause unambiguous, well-known price splits (e.g., iPhone storage tiers, electric vs acoustic instruments).
- Assume authenticity of the product unless otherwise stated or implied with "-style" or "-like" or similar.

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
