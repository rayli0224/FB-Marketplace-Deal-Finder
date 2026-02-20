"""Prompts for FB listing filter (pre-filtering step)."""

from src.evaluation.listing_format import format_fb_listing_for_prompt

SYSTEM_MESSAGE = "You are an expert at evaluating marketplace listings. Always respond with valid JSON only."


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
