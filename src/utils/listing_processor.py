"""
Listing processor for evaluating individual Facebook Marketplace listings.

Processes a single FB listing by generating an optimized eBay search query,
fetching comparable prices from eBay, and calculating a deal score. Returns the
listing with deal score (or None when eBay data or calculation fails). All
listings are returned regardless of threshold or eBay data availability.
"""

from typing import Dict, Optional

from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import calculate_deal_score
from src.utils.openai_helpers import generate_ebay_query_for_listing, filter_ebay_results_with_openai
from src.utils.colored_logger import setup_colored_logger, log_substep_sep, log_data_line, log_step_title, set_step_indent, clear_step_indent, wait_status
import statistics

logger = setup_colored_logger("listing_processor")


def _listing_result(
    listing: Listing,
    deal_score: Optional[float],
    ebay_search_query: Optional[str] = None,
    comp_price: Optional[float] = None,
    comp_prices: Optional[list] = None,
    comp_items: Optional[list] = None,
) -> Dict:
    """
    Build the result dict for a processed listing.

    Always includes title, price, location, url, and dealScore. Adds
    ebaySearchQuery, compPrice, compPrices, and compItems only when the
    corresponding arguments are not None, so the API can omit transparency
    fields when eBay data was unavailable.
    """
    out = {
        "title": listing.title,
        "price": listing.price,
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
    return out


def process_single_listing(
    listing: Listing,
    original_query: str,
    threshold: float = 20.0,
    n_items: int = 50,
    listing_index: Optional[int] = None,
    total_listings: Optional[int] = None
) -> Dict:
    """
    Process a single FB listing: generate eBay query via OpenAI, fetch comparable
    prices, and calculate deal score (percentage savings vs eBay average).
    Returns listing dict with dealScore. When eBay stats are missing or calculation
    fails, dealScore is None so the UI shows "--".
    """
    progress = f"[{listing_index}/{total_listings}] " if (listing_index is not None and total_listings is not None) else ""
    log_substep_sep(logger, f"{progress}FB listing: {listing.title}")
    set_step_indent("  ")
    try:
        log_data_line(logger, "Data", price=listing.price, location=listing.location, url=listing.url)
        logger.debug(f"Description: {listing.description}")

        log_step_title(logger, "Step 1: Generating eBay query")
        with wait_status(logger, "eBay query (OpenAI)"):
            query_result = generate_ebay_query_for_listing(listing, original_query)
        if not query_result:
            logger.warning("Failed to generate eBay query — unknown deal score")
            return _listing_result(listing, None)

        enhanced_query, exclusion_keywords = query_result

        log_step_title(logger, f"Step 2: Fetching eBay prices — '{enhanced_query}'")
        with wait_status(logger, "eBay prices"):
            ebay_stats = get_market_price(
                search_term=enhanced_query,
                n_items=n_items,
                excluded_keywords=exclusion_keywords,
            )

        if not ebay_stats:
            logger.warning("No eBay stats — unknown deal score")
            return _listing_result(listing, None)
        logger.info(f"Found {ebay_stats.sample_size} eBay listings, avg ${ebay_stats.average:.2f}")

        log_step_title(logger, "Step 3: Filtering eBay results for comparability")
        ebay_items = getattr(ebay_stats, "item_summaries", None)
        all_items_with_filter_flag = None
        if ebay_items:
            with wait_status(logger, "Filtering eBay results (OpenAI)"):
                filtered_items = filter_ebay_results_with_openai(listing, ebay_items)
            if filtered_items is not None:
                # Create a set of filtered item URLs for quick lookup
                filtered_urls = {item.get("url", "") for item in filtered_items}

                # Mark all items with filtered flag
                all_items_with_filter_flag = [
                    {**item, "filtered": item.get("url", "") not in filtered_urls}
                    for item in ebay_items
                ]

                if len(filtered_items) != len(ebay_items):
                    # Recalculate stats from filtered items (even if below minimum)
                    filtered_prices = [item["price"] for item in filtered_items]
                    if len(filtered_prices) >= 3:
                        ebay_stats.raw_prices = sorted(filtered_prices)
                        ebay_stats.average = statistics.mean(filtered_prices)
                        ebay_stats.sample_size = len(filtered_prices)
                        # Use all items (with filter flags) for display, but stats are from filtered only
                        ebay_stats.item_summaries = all_items_with_filter_flag
                        logger.info(f"Filtered to {ebay_stats.sample_size} comparable, avg ${ebay_stats.average:.2f}")
                    elif len(filtered_prices) > 0:
                        # Use filtered items even if below minimum - better than using non-comparable items
                        ebay_stats.raw_prices = sorted(filtered_prices)
                        ebay_stats.average = statistics.mean(filtered_prices)
                        ebay_stats.sample_size = len(filtered_prices)
                        ebay_stats.item_summaries = all_items_with_filter_flag
                        logger.warning(f"Filtering left {ebay_stats.sample_size} items (below minimum 3)")
                    else:
                        # No items passed filtering - cannot calculate meaningful stats
                        # Still show all items with filter flags so user can see what was filtered
                        logger.warning("All items filtered out — cannot calculate comparison")
                        # Invalidate stats so deal_score calculation will fail
                        ebay_stats.average = 0
                        ebay_stats.sample_size = 0
                        ebay_stats.raw_prices = []
                        ebay_stats.item_summaries = all_items_with_filter_flag
                else:
                    logger.debug(f"   All items deemed comparable")
                    # All items are comparable, mark none as filtered
                    all_items_with_filter_flag = [
                        {**item, "filtered": False}
                        for item in ebay_items
                    ]
                    ebay_stats.item_summaries = all_items_with_filter_flag
            else:
                logger.debug("   Filtering unavailable (OpenAI not configured) - using original results")
                # Mark all items as not filtered when filtering is unavailable
                if ebay_items:
                    all_items_with_filter_flag = [
                        {**item, "filtered": False}
                        for item in ebay_items
                    ]

        log_step_title(logger, "Step 4: Calculating deal score")
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        if deal_score is None:
            logger.warning("Could not calculate deal score — unknown")
            return _listing_result(listing, None)

        logger.info(f"Deal score: {deal_score:.1f}% savings vs eBay avg")
        if deal_score >= threshold:
            logger.info(f"Deal: {deal_score:.1f}% (FB ${listing.price:.2f} vs eBay avg ${ebay_stats.average:.2f})")
        else:
            logger.info(f"Below threshold ({deal_score:.1f}% < {threshold}%)")

        comp_items = all_items_with_filter_flag if all_items_with_filter_flag is not None else getattr(ebay_stats, "item_summaries", None)
        return _listing_result(
            listing,
            deal_score,
            ebay_search_query=enhanced_query,
            comp_price=ebay_stats.average,
            comp_prices=ebay_stats.raw_prices,
            comp_items=comp_items,
        )
    finally:
        clear_step_indent()
