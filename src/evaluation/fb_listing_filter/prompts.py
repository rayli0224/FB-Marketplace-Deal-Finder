"""Prompts for FB listing filter (pre-filtering step)."""

SYSTEM_MESSAGE = """You are evaluating raw Facebook Marketplace listings to decide whether they are worth investigating further.

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


def get_pre_filtering_prompt(fb_listing_text: str) -> str:
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
