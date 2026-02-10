"""
Listing processor for evaluating individual Facebook Marketplace listings.

Processes a single FB listing by generating an optimized eBay search query,
fetching comparable prices from eBay, and calculating a deal score. Returns the
listing with deal score (or None when eBay data or calculation fails). All
listings are returned regardless of threshold or eBay data availability.
"""

from typing import Dict, Optional

from src.scrapers.fb_marketplace_scraper import Listing
from src.scrapers.ebay_scraper import get_market_price, DEFAULT_EBAY_ITEMS
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
    n_items: int = DEFAULT_EBAY_ITEMS,
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

        enhanced_query, browse_api_parameters = query_result

        log_step_title(logger, f"Step 2: Fetching eBay prices — '{enhanced_query}'")
        if browse_api_parameters:
            logger.info("Using Browse API parameters from OpenAI")
        with wait_status(logger, "eBay prices"):
            ebay_stats = get_market_price(
                search_term=enhanced_query,
                n_items=n_items,
                browse_api_parameters=browse_api_parameters,
            )

        if not ebay_stats:
            logger.warning("No eBay stats — unknown deal score")
            return _listing_result(listing, None)
        if ebay_stats.sample_size < 3:
            logger.warning(f"Found only {ebay_stats.sample_size} eBay listing(s) (small sample size)")
        logger.info(f"Found {ebay_stats.sample_size} eBay listings, avg ${ebay_stats.average:.2f}")

        log_step_title(logger, "Step 3: Filtering eBay results for comparability")
        ebay_items = getattr(ebay_stats, "item_summaries", None)
        all_items_with_filter_flag = None
        if ebay_items:
            with wait_status(logger, "Filtering eBay results (OpenAI)"):
                filter_result = filter_ebay_results_with_openai(listing, ebay_items)
            if filter_result is not None:
                comparable_indices, filtered_items, filter_reasons = filter_result
                
                # Mark items based on whether their 1-based index is in comparable_indices
                comparable_indices_set = set(comparable_indices)
                all_items_with_filter_flag = []
                for i, item in enumerate(ebay_items):
                    item_idx = i + 1  # 1-based index
                    reason = filter_reasons.get(str(item_idx), "")
                    is_filtered = item_idx not in comparable_indices_set
                    item_with_flags = {
                        **item,
                        "filtered": is_filtered,
                    }
                    if reason:
                        item_with_flags["filterReason"] = reason
                    all_items_with_filter_flag.append(item_with_flags)
                
                # Recalculate stats from filtered items
                if len(filtered_items) != len(ebay_items):
                    filtered_prices = [item["price"] for item in filtered_items]
                    if len(filtered_prices) >= 3:
                        ebay_stats.raw_prices = sorted(filtered_prices)
                        ebay_stats.average = statistics.mean(filtered_prices)
                        ebay_stats.sample_size = len(filtered_prices)
                        ebay_stats.item_summaries = all_items_with_filter_flag
                        logger.info(f"Filtered to {ebay_stats.sample_size} comparable, avg ${ebay_stats.average:.2f}")
                    elif len(filtered_prices) > 0:
                        ebay_stats.raw_prices = sorted(filtered_prices)
                        ebay_stats.average = statistics.mean(filtered_prices)
                        ebay_stats.sample_size = len(filtered_prices)
                        ebay_stats.item_summaries = all_items_with_filter_flag
                        logger.warning(f"Filtering left {ebay_stats.sample_size} items (below minimum 3)")
                    else:
                        logger.warning("All items filtered out — cannot calculate comparison")
                        ebay_stats.average = 0
                        ebay_stats.sample_size = 0
                        ebay_stats.raw_prices = []
                        ebay_stats.item_summaries = all_items_with_filter_flag
                else:
                    logger.debug("All items deemed comparable")
                    ebay_stats.item_summaries = all_items_with_filter_flag
            else:
                logger.debug("Filtering unavailable (OpenAI not configured) - using original results")
                if ebay_items:
                    all_items_with_filter_flag = [
                        {**item, "filtered": False}
                        for item in ebay_items
                    ]
                    ebay_stats.item_summaries = all_items_with_filter_flag

        log_step_title(logger, "Step 4: Calculating deal score")
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        comp_items = all_items_with_filter_flag if all_items_with_filter_flag is not None else getattr(ebay_stats, "item_summaries", None)

        if deal_score is None:
            logger.warning("Could not calculate deal score — unknown")
            return _listing_result(
                listing,
                None,
                ebay_search_query=enhanced_query,
                comp_price=ebay_stats.average if ebay_stats.average > 0 else None,
                comp_prices=ebay_stats.raw_prices if ebay_stats.raw_prices else None,
                comp_items=comp_items,
            )

        logger.info(f"Deal score: {deal_score:.1f}% savings vs eBay avg")
        if deal_score >= threshold:
            logger.info(f"Deal: {deal_score:.1f}% (FB ${listing.price:.2f} vs eBay avg ${ebay_stats.average:.2f})")
        else:
            logger.info(f"Below threshold ({deal_score:.1f}% < {threshold}%)")

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
