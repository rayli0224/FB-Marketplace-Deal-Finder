"""Prompts for eBay results filter step."""

SYSTEM_MESSAGE = "You are an expert at comparing products across marketplaces. Always respond with valid JSON only."


def get_batch_filtering_prompt(product_recon_json: str, ebay_items_text: str) -> str:
    """Generate the prompt for filtering a batch of eBay items against a grounded product."""
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
Use the `key_attributes` array from the product details to determine which attributes matter and their price impact. The product details includes structured attributes with `price_impact` values ("high", "medium", "low").

**Focus on high-impact attributes:** Differences in high-impact attributes (e.g., storage capacity for electronics, generation/year for devices) should lead to rejection. Differences in low-impact attributes (e.g., color for most products) are acceptable.

**If `key_attributes` is missing or empty:** Fall back to general category guidelines:
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
