"""Prompts for eBay query generation step."""

SYSTEM_MESSAGE = "You are an expert at creating precise search queries for online marketplaces. Always respond with valid JSON only."


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
