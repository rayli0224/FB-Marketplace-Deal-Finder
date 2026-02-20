"""
Evaluation orchestrator — parent for the full evaluation pipeline.

Runs: FB filter → internet enrichment → eBay query generation → eBay search → eBay result filter → deal score.
Calls step modules only; contains orchestration logic only.
"""

import threading
from _thread import LockType
from typing import Callable, Dict, Optional, Tuple

from src.scrapers.fb_marketplace_scraper import Listing, SearchCancelledError
from src.scrapers.ebay_scraper_v2 import (
    EbaySoldScraper,
    DEFAULT_EBAY_ITEMS,
    get_market_price_cached,
)
from src.evaluation.deal_calculator import calculate_deal_score_for_listing
from src.evaluation.fb_listing_filter import filter_fb_listing
from src.evaluation.internet_enrichment import enrich_listing_with_internet
from src.evaluation.ebay_query_generator import generate_ebay_query
from src.evaluation.ebay_results_filter import filter_ebay_results_for_listing
from src.evaluation.result_builder import build_listing_result
from src.utils.colored_logger import (
    setup_colored_logger,
    log_data_block,
    log_listing_box_sep,
    log_warning,
    set_step_indent,
    clear_step_indent,
    wait_status,
)

logger = setup_colored_logger("evaluation_orchestrator")


def generate_ebay_query_for_listing(
    listing: Listing,
    original_query: str,
    on_product_recon: Optional[Callable[[dict, list[dict]], None]] = None,
) -> Optional[Tuple[Optional[str], Optional[str], Optional[str]]]:
    """
    Run the query pipeline: FB filter → internet enrichment → eBay query generation.

    Returns (enhanced_query, skip_reason, product_recon_json) or None on failure.
    """
    reject_reason = filter_fb_listing(listing)
    if reject_reason is not None:
        return (None, reject_reason, None)

    product_recon_json = enrich_listing_with_internet(listing, on_product_recon=on_product_recon)
    if product_recon_json is None:
        return None

    enhanced_query = generate_ebay_query(product_recon_json, original_query)
    if enhanced_query is None:
        return None

    return (enhanced_query, None, product_recon_json)


def compare_listing_to_ebay(
    listing: Listing,
    original_query: str,
    threshold: float = 20.0,  # kept for API compatibility; frontend filters by threshold
    n_items: int = DEFAULT_EBAY_ITEMS,
    listing_index: Optional[int] = None,
    total_listings: Optional[int] = None,
    cancelled: Optional[threading.Event] = None,
    ebay_scraper: Optional[EbaySoldScraper] = None,
    market_price_cache: Optional[dict] = None,
    market_price_cache_lock: Optional[LockType] = None,
    on_query_generated: Optional[Callable[[str], None]] = None,
    on_product_recon: Optional[Callable[[dict, list[dict]], None]] = None,
) -> Dict:
    """
    Compare a single FB listing to eBay sold prices and compute deal score.

    Orchestrates: generate_ebay_query_for_listing → get_market_price_cached → filter_ebay_results_for_listing → calculate_deal_score_for_listing.
    """
    if listing_index is not None and total_listings is not None:
        progress = f"[{listing_index}/{total_listings}] "
    elif listing_index is not None:
        progress = f"[{listing_index}/n] "
    else:
        progress = ""
    logger.info(f"{progress}FB listing: {listing.title}")
    set_step_indent("  ")
    try:
        return _evaluate_listing(
            listing,
            original_query,
            n_items,
            cancelled,
            ebay_scraper,
            market_price_cache,
            market_price_cache_lock,
            on_query_generated,
            on_product_recon,
        )
    except SearchCancelledError:
        raise
    except Exception as e:
        log_warning(logger, f"Error comparing listing to eBay: {e}")
        return build_listing_result(listing, None, no_comp_reason="Unable to generate eBay comparisons")
    finally:
        clear_step_indent()
        log_listing_box_sep(logger)


def _evaluate_listing(
    listing: Listing,
    original_query: str,
    n_items: int,
    cancelled: Optional[threading.Event] = None,
    ebay_scraper: Optional[EbaySoldScraper] = None,
    market_price_cache: Optional[dict] = None,
    market_price_cache_lock: Optional[LockType] = None,
    on_query_generated: Optional[Callable[[str], None]] = None,
    on_product_recon: Optional[Callable[[dict, list[dict]], None]] = None,
) -> Dict:
    """Orchestrate step calls only."""
    log_data_block(logger, "Data", price=listing.price, location=listing.location, url=listing.url)
    if listing.description:
        logger.debug(f"  Description: {listing.description}")

    with wait_status(logger, "eBay search"):
        query_result = generate_ebay_query_for_listing(
            listing, original_query, on_product_recon=on_product_recon
        )
    if query_result is None:
        log_warning(logger, "Could not prepare search — skipping deal score")
        return build_listing_result(listing, None, no_comp_reason="Could not prepare search")
    enhanced_query, skip_reason, product_recon_json = query_result
    if skip_reason is not None:
        return build_listing_result(listing, None, no_comp_reason=skip_reason)
    if not product_recon_json:
        log_warning(logger, "Could not research item details — skipping deal score")
        return build_listing_result(listing, None, no_comp_reason="Could not prepare search")
    if on_query_generated is not None:
        on_query_generated(enhanced_query)

    with wait_status(logger, "eBay prices"):
        ebay_stats, from_cache = get_market_price_cached(
            enhanced_query, n_items, ebay_scraper, market_price_cache, market_price_cache_lock, cancelled
        )
    if from_cache:
        logger.info("Using saved eBay prices for matching search")
    if not ebay_stats:
        log_warning(logger, "No eBay results — skipping deal score")
        return build_listing_result(listing, None, no_comp_reason="No similar items found on eBay")
    if ebay_stats.sample_size < 3:
        log_warning(logger, f"Only {ebay_stats.sample_size} similar listing(s) — small sample")
    logger.info(f"📋 {ebay_stats.sample_size} similar listings on eBay (avg ${ebay_stats.average:.2f})")

    with wait_status(logger, "matching listings"):
        filtered_stats, no_comp_reason = filter_ebay_results_for_listing(
            listing, ebay_stats, product_recon_json=product_recon_json, cancelled=cancelled
        )

    if no_comp_reason == "no_comparable":
        return build_listing_result(
            listing,
            None,
            ebay_search_query=enhanced_query,
            comp_items=filtered_stats.item_summaries,
            no_comp_reason="No comparable eBay listings matched this item",
        )

    deal_score = calculate_deal_score_for_listing(listing, filtered_stats)
    comp_items = filtered_stats.item_summaries

    if deal_score is None:
        log_warning(logger, "Could not compare price")
        return build_listing_result(
            listing,
            None,
            ebay_search_query=enhanced_query,
            comp_price=filtered_stats.average if filtered_stats.average > 0 else None,
            comp_prices=filtered_stats.raw_prices if filtered_stats.raw_prices else None,
            comp_items=comp_items,
            no_comp_reason="Not enough comparable listings to calculate price",
        )

    return build_listing_result(
        listing,
        deal_score,
        ebay_search_query=enhanced_query,
        comp_price=filtered_stats.average,
        comp_prices=filtered_stats.raw_prices,
        comp_items=comp_items,
    )
