"""
Compares a Facebook Marketplace listing to eBay sold prices and computes deal score.

Takes a single FB listing, generates an eBay search query, fetches comparable sold
prices, filters to true matches, and calculates the deal score (percentage savings vs
eBay average). Returns the listing with deal score and comparison data.
"""

from typing import Dict, Optional
import asyncio
import threading

from src.scrapers.fb_marketplace_scraper import Listing, SearchCancelledError
from src.scrapers.ebay_scraper_v2 import get_market_price, DEFAULT_EBAY_ITEMS
from src.evaluation.deal_calculator import calculate_deal_score
from src.evaluation.ebay_query_generator import generate_ebay_query_for_listing
from src.evaluation.ebay_result_filter import filter_ebay_results_with_openai
from src.utils.colored_logger import setup_colored_logger, log_data_block, log_listing_box_sep, log_warning, set_step_indent, clear_step_indent, wait_status
import statistics

logger = setup_colored_logger("listing_ebay_comparison")


def _listing_result(
    listing: Listing,
    deal_score: Optional[float],
    ebay_search_query: Optional[str] = None,
    comp_price: Optional[float] = None,
    comp_prices: Optional[list] = None,
    comp_items: Optional[list] = None,
    no_comp_reason: Optional[str] = None,
) -> Dict:
    """
    Build the result dict for a compared listing.

    Always includes title, price, location, url, and dealScore. Adds
    ebaySearchQuery, compPrice, compPrices, and compItems only when the
    corresponding arguments are not None. Adds noCompReason when the listing
    could not be compared and we have a user-facing explanation.
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
    if no_comp_reason is not None:
        out["noCompReason"] = no_comp_reason
    return out


def compare_listing_to_ebay(
    listing: Listing,
    original_query: str,
    threshold: float = 20.0,
    n_items: int = DEFAULT_EBAY_ITEMS,
    listing_index: Optional[int] = None,
    total_listings: Optional[int] = None,
    cancelled: Optional[threading.Event] = None,
    ebay_scraper=None,
) -> Dict:
    """
    Compare a single FB listing to eBay sold prices and compute deal score.

    Generates an eBay search query from the listing, fetches comparable sold prices,
    filters to true matches, and calculates percentage savings vs eBay average.
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
        return _compare_listing_to_ebay_inner(
            listing, original_query, threshold, n_items, cancelled, ebay_scraper
        )
    except SearchCancelledError:
        raise
    except Exception as e:
        log_warning(logger, f"Error comparing listing to eBay: {e}")
        return _listing_result(listing, None, no_comp_reason="Unable to generate eBay comparisons")
    finally:
        clear_step_indent()
        log_listing_box_sep(logger)


def _compare_listing_to_ebay_inner(
    listing: Listing,
    original_query: str,
    threshold: float,
    n_items: int,
    cancelled: Optional[threading.Event] = None,
    ebay_scraper=None,
) -> Dict:
    """Inner comparison logic. Caller handles exceptions and returns fallback result."""
    log_data_block(logger, "Data", price=listing.price, location=listing.location, url=listing.url)
    if listing.description:
        logger.debug(f"  Description: {listing.description}")

    logger.info("💡 Preparing eBay search")
    with wait_status(logger, "eBay search"):
        query_result = generate_ebay_query_for_listing(listing, original_query)
    if query_result is None:
        log_warning(logger, "Could not prepare search — skipping deal score")
        return _listing_result(listing, None, no_comp_reason="Could not prepare search")
    enhanced_query, skip_reason = query_result
    if skip_reason is not None:
        return _listing_result(listing, None, no_comp_reason=skip_reason)

    logger.info("💰 Searching eBay for similar items")
    with wait_status(logger, "eBay prices"):
        ebay_stats = get_market_price(
            search_term=enhanced_query,
            n_items=n_items,
            scraper=ebay_scraper,
            cancelled=cancelled,
        )

    if not ebay_stats:
        log_warning(logger, "No eBay results — skipping deal score")
        return _listing_result(listing, None, no_comp_reason="No similar items found on eBay")
    if ebay_stats.sample_size < 3:
        log_warning(logger, f"Only {ebay_stats.sample_size} similar listing(s) — small sample")
    logger.info(f"📋 {ebay_stats.sample_size} similar listings on eBay (avg ${ebay_stats.average:.2f})")

    logger.info("🔍 Keeping only true matches")
    ebay_items = getattr(ebay_stats, "item_summaries", None)
    all_items_with_filter_flag = None
    if ebay_items:
        with wait_status(logger, "matching listings"):
            filter_result = filter_ebay_results_with_openai(listing, ebay_items, cancelled=cancelled)
        if filter_result is not None and asyncio.iscoroutine(filter_result):
            log_warning(logger, "Filter returned coroutine instead of result — using all listings")
            filter_result = None
        if filter_result is not None:
            accept_indices, maybe_indices, filtered_items, decisions = filter_result

            accept_indices_set = set(accept_indices)
            maybe_indices_set = set(maybe_indices)
            all_items_with_filter_flag = []
            for i, item in enumerate(ebay_items):
                item_idx = i + 1  # 1-based index
                decision_info = decisions.get(str(item_idx), {})
                decision = decision_info.get("decision", "accept")
                reason = decision_info.get("reason", "")
                
                # filterStatus: "accept", "maybe", or "reject"
                # filtered: True only for rejected items (backwards compatibility)
                is_rejected = decision == "reject"
                item_with_flags = {
                    **item,
                    "filtered": is_rejected,
                    "filterStatus": decision,
                }
                if reason:
                    item_with_flags["filterReason"] = reason
                all_items_with_filter_flag.append(item_with_flags)

            # Calculate weighted average: accept=1.0 weight, maybe=0.5 weight
            weighted_sum = 0.0
            total_weight = 0.0
            for i, item in enumerate(ebay_items):
                item_idx = i + 1
                if item_idx in accept_indices_set:
                    weighted_sum += item["price"] * 1.0
                    total_weight += 1.0
                elif item_idx in maybe_indices_set:
                    weighted_sum += item["price"] * 0.5
                    total_weight += 0.5

            if len(filtered_items) != len(ebay_items) or maybe_indices:
                # Get prices for logging (unweighted list of kept items)
                filtered_prices = [item["price"] for item in filtered_items]
                
                if total_weight >= 3.0:
                    ebay_stats.raw_prices = sorted(filtered_prices)
                    ebay_stats.average = weighted_sum / total_weight
                    ebay_stats.sample_size = len(filtered_items)
                    ebay_stats.item_summaries = all_items_with_filter_flag
                    logger.info(f"📋 {len(accept_indices)} accept + {len(maybe_indices)} maybe (weighted avg ${ebay_stats.average:.2f})")
                elif total_weight > 0:
                    ebay_stats.raw_prices = sorted(filtered_prices)
                    ebay_stats.average = weighted_sum / total_weight
                    ebay_stats.sample_size = len(filtered_items)
                    ebay_stats.item_summaries = all_items_with_filter_flag
                    log_warning(logger, f"Only {len(accept_indices)} accept + {len(maybe_indices)} maybe (need more to compare reliably)")
                else:
                    log_warning(logger, "No matching listings — can't compare price")
                    ebay_stats.average = 0
                    ebay_stats.sample_size = 0
                    ebay_stats.raw_prices = []
                    ebay_stats.item_summaries = all_items_with_filter_flag
                    return _listing_result(
                        listing,
                        None,
                        ebay_search_query=enhanced_query,
                        comp_items=all_items_with_filter_flag,
                        no_comp_reason="No comparable eBay listings matched this item",
                    )
            else:
                logger.debug("All items deemed comparable")
                ebay_stats.item_summaries = all_items_with_filter_flag
        else:
            logger.debug("Filtering unavailable (OpenAI not configured) - using original results")
            if ebay_items:
                all_items_with_filter_flag = [
                    {**item, "filtered": False, "filterStatus": "accept"}
                    for item in ebay_items
                ]
                ebay_stats.item_summaries = all_items_with_filter_flag

    logger.info("📊 Comparing price")
    deal_score = calculate_deal_score(listing.price, ebay_stats)
    comp_items = all_items_with_filter_flag if all_items_with_filter_flag is not None else getattr(ebay_stats, "item_summaries", None)

    if deal_score is None:
        log_warning(logger, "Could not compare price")
        return _listing_result(
            listing,
            None,
            ebay_search_query=enhanced_query,
            comp_price=ebay_stats.average if ebay_stats.average > 0 else None,
            comp_prices=ebay_stats.raw_prices if ebay_stats.raw_prices else None,
            comp_items=comp_items,
            no_comp_reason="Not enough comparable listings to calculate price",
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
