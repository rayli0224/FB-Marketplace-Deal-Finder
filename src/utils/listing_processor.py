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
from src.utils.colored_logger import setup_colored_logger, log_data_block, log_listing_box_sep, set_step_indent, clear_step_indent, wait_status
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
    if listing.image_base64:
        out["listingImageDataUrl"] = f"data:image/jpeg;base64,{listing.image_base64}"
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
    if listing_index is not None and total_listings is not None:
        progress = f"[{listing_index}/{total_listings}] "
    elif listing_index is not None:
        progress = f"[{listing_index}/n] "
    else:
        progress = ""
    log_listing_box_sep(logger)
    logger.info(f"{progress}FB listing: {listing.title}")
    set_step_indent("  ")
    try:
        log_data_block(logger, "Data", price=listing.price, location=listing.location, url=listing.url)
        if listing.description:
            logger.debug(f"  Description: {listing.description}")

        logger.info("💡 Preparing eBay search")
        with wait_status(logger, "eBay search"):
            query_result = generate_ebay_query_for_listing(listing, original_query)
        if not query_result:
            logger.warning("Could not prepare search — skipping deal score")
            return _listing_result(listing, None)

        enhanced_query, browse_api_parameters = query_result

        logger.info("💰 Searching eBay for similar items")
        with wait_status(logger, "eBay prices"):
            ebay_stats = get_market_price(
                search_term=enhanced_query,
                n_items=n_items,
                browse_api_parameters=browse_api_parameters,
                image_base64=listing.image_base64,
            )

        if not ebay_stats:
            logger.warning("No eBay results — skipping deal score")
            return _listing_result(listing, None)
        if ebay_stats.sample_size < 3:
            logger.warning(f"Only {ebay_stats.sample_size} similar listing(s) — small sample")
        logger.info(f"📋 {ebay_stats.sample_size} similar listings on eBay (avg ${ebay_stats.average:.2f})")

        logger.info("🔍 Keeping only true matches")
        ebay_items = getattr(ebay_stats, "item_summaries", None)
        all_items_with_filter_flag = None
        if ebay_items:
            with wait_status(logger, "matching listings"):
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
                        logger.info(f"📋 {ebay_stats.sample_size} matches (avg ${ebay_stats.average:.2f})")
                    elif len(filtered_prices) > 0:
                        ebay_stats.raw_prices = sorted(filtered_prices)
                        ebay_stats.average = statistics.mean(filtered_prices)
                        ebay_stats.sample_size = len(filtered_prices)
                        ebay_stats.item_summaries = all_items_with_filter_flag
                        logger.warning(f"Only {ebay_stats.sample_size} matches (need at least 3 to compare)")
                    else:
                        logger.warning("No matching listings — can't compare price")
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

        logger.info("📊 Comparing price")
        deal_score = calculate_deal_score(listing.price, ebay_stats)
        comp_items = all_items_with_filter_flag if all_items_with_filter_flag is not None else getattr(ebay_stats, "item_summaries", None)

        if deal_score is None:
            logger.warning("Could not compare price")
            return _listing_result(
                listing,
                None,
                ebay_search_query=enhanced_query,
                comp_price=ebay_stats.average if ebay_stats.average > 0 else None,
                comp_prices=ebay_stats.raw_prices if ebay_stats.raw_prices else None,
                comp_items=comp_items,
            )

        logger.info(f"📊 {deal_score:.1f}% below typical eBay price")
        if deal_score >= threshold:
            logger.info(f"✅ Good deal: {deal_score:.1f}% (FB ${listing.price:.2f} vs eBay avg ${ebay_stats.average:.2f})")
        else:
            logger.info(f"⚠️ Not a big enough deal (under {threshold}% savings)")

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
        log_listing_box_sep(logger)
