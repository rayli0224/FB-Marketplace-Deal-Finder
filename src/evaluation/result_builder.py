"""
Builds the evaluation result dict for a compared listing.
"""

from typing import Dict, Optional

from src.scrapers.fb_marketplace_scraper import Listing


def build_listing_result(
    listing: Listing,
    deal_score: Optional[float],
    *,
    ebay_search_query: Optional[str] = None,
    comp_price: Optional[float] = None,
    comp_prices: Optional[list] = None,
    comp_items: Optional[list] = None,
    no_comp_reason: Optional[str] = None,
) -> Dict:
    """
    Build the evaluation result dict for a compared listing.

    Always includes title, price, currency, location, url, dealScore. Adds optional
    fields (ebaySearchQuery, compPrice, compPrices, compItems, noCompReason) only
    when provided.
    """
    out = {
        "title": listing.title,
        "price": listing.price,
        "currency": listing.currency,
        "location": listing.location,
        "url": listing.url,
        "dealScore": deal_score,
    }
    if ebay_search_query is not None:
        out["ebaySearchQuery"] = ebay_search_query
    if comp_price is not None:
        out["compPrice"] = comp_price
    if comp_prices is not None:
        out["compPrices"] = comp_prices
    if comp_items is not None:
        out["compItems"] = comp_items
    if no_comp_reason is not None:
        out["noCompReason"] = no_comp_reason
    return out
