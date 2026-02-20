"""Prompts for internet enrichment (product recon step)."""

from src.evaluation.listing_format import format_fb_listing_for_prompt

SYSTEM_MESSAGE = "You are an expert at identifying real-world products from marketplace listings. Always respond with valid JSON only."


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
