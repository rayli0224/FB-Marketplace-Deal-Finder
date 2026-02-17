"""
SSE streaming search: scrapes FB Marketplace, evaluates each listing against eBay, and
streams progress events to the frontend in real time.

Manages background threads for FB scraping and eBay evaluation, bridges them to an
SSE generator via a queue, and handles cancellation and cleanup.
"""

import json
import logging
import queue
import threading
import time
import concurrent.futures
from typing import Optional

from src.scrapers.fb_marketplace_scraper import (
    search_marketplace as search_fb_marketplace,
    FacebookNotLoggedInError,
    LocationNotFoundError,
    SearchCancelledError,
    force_close_active_scraper,
)
from src.scrapers.ebay_scraper_v2 import (
    DEFAULT_EBAY_ITEMS,
    EbayScraperPool,
)
from src.evaluation.listing_ebay_comparison import compare_listing_to_ebay
from src.evaluation.fb_listing_filter import is_suspicious_price
from src.utils.colored_logger import setup_colored_logger, log_step_sep, log_error_short, log_warning
from src.utils.search_runtime_config import (
    LISTING_EVAL_MAX_WORKERS,
    LISTING_EVAL_WORKER_START_DELAY_SEC,
    EVAL_WAIT_TIMEOUT_SEC,
)

from src.server.search_state import (
    cancel_and_wait_for_previous_search,
    kill_lingering_chrome,
    set_active_search,
    mark_search_starting,
    mark_search_complete,
)

logger = setup_colored_logger("server")

_EVENT_INSPECTOR_URL = "inspector_url"

# Loggers that receive the queue handler in debug mode.
_DEBUG_LOG_LOGGER_NAMES = ("server", "fb_scraper", "listing_ebay_comparison", "ebay_query_generator", "ebay_result_filter", "ebay_scraper_v2")


class QueueLogHandler(logging.Handler):
    """
    Logging handler that pushes log records into a queue as debug_log events.
    Used when DEBUG_MODE is on so the frontend can show logs for the current search.
    """

    def __init__(self, event_queue: queue.Queue):
        super().__init__()
        self._event_queue = event_queue
        self._buffer_lock = threading.Lock()
        self._buffered_thread_labels: dict[int, str] = {}
        self._buffered_thread_lines: dict[int, list[str]] = {}

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()
            if not msg:
                return
            thread_id = record.thread
            with self._buffer_lock:
                if thread_id in self._buffered_thread_labels:
                    self._buffered_thread_lines.setdefault(thread_id, []).append(msg)
                    return
            if msg:
                self._event_queue.put({
                    "type": "debug_log",
                    "level": record.levelname,
                    "message": msg,
                })
        except Exception:
            pass

    def start_thread_buffer(self, thread_id: int, label: str):
        """
        Start buffering debug logs for a worker thread.

        Emits a single start line immediately, then holds all intermediate log
        lines until finish_thread_buffer is called.
        """
        with self._buffer_lock:
            self._buffered_thread_labels[thread_id] = label
            self._buffered_thread_lines[thread_id] = []
        self._event_queue.put({
            "type": "debug_log",
            "level": "INFO",
            "message": f"▶️ {label}",
        })

    def finish_thread_buffer(self, thread_id: int, outcome: str):
        """
        Flush buffered logs for a worker thread with a completion outcome.

        Outcome should be one of: "done", "failed", "cancelled".
        """
        with self._buffer_lock:
            label = self._buffered_thread_labels.pop(thread_id, None)
            lines = self._buffered_thread_lines.pop(thread_id, [])

        if not label:
            return

        for line in lines:
            self._event_queue.put({
                "type": "debug_log",
                "level": "INFO",
                "message": line,
            })

        if outcome == "done":
            end_message = f"✅ Finished {label}"
        elif outcome == "cancelled":
            end_message = f"⚠️ Cancelled {label}"
        else:
            end_message = f"⚠️ Finished with issues {label}"
        self._event_queue.put({
            "type": "debug_log",
            "level": "INFO",
            "message": end_message,
        })


def create_search_stream(request, debug_mode: bool):
    """
    Create an SSE event generator that streams search progress to the frontend.

    Cancels any previous search, launches FB scraping in a background thread,
    then evaluates each listing against eBay in another thread, streaming
    progress/results as SSE events throughout.
    """
    cancel_and_wait_for_previous_search()
    kill_lingering_chrome()

    event_queue = queue.Queue()
    fb_evaluable_listings = []
    cancelled = threading.Event()

    mark_search_starting()

    debug_log_handler = None
    if debug_mode:
        debug_log_handler = QueueLogHandler(event_queue)
        debug_log_handler.setLevel(logging.DEBUG)
        for name in _DEBUG_LOG_LOGGER_NAMES:
            logging.getLogger(name).addHandler(debug_log_handler)

    location_info_req = request.zipCode
    log_step_sep(logger, f"Search request — query='{request.query}', location={location_info_req}, radius={request.radius}mi")

    filtered_count_holder = [0]
    fb_listing_id_counter = 0

    def _next_fb_listing_id() -> str:
        """Return a stable backend-only listing id for this search run."""
        nonlocal fb_listing_id_counter
        fb_listing_id_counter += 1
        return f"fb-{fb_listing_id_counter}"

    def build_debug_listing_dict(listing, fb_listing_id: str, filtered: bool = False) -> dict:
        """Build the dict payload for a debug_facebook_listing SSE event."""
        entry = {
            "fbListingId": fb_listing_id,
            "title": listing.title,
            "price": listing.price,
            "location": listing.location,
            "url": listing.url,
            "description": listing.description or "",
        }
        if filtered:
            entry["filtered"] = True
        return entry

    def on_listing_found(listing, count):
        if cancelled.is_set():
            return
        fb_listing_id = _next_fb_listing_id()
        fb_evaluable_listings.append((fb_listing_id, listing))
        event_queue.put({"type": "progress", "scannedCount": count})
        if debug_mode:
            event_queue.put(
                {
                    "type": "debug_facebook_listing",
                    "listing": build_debug_listing_dict(listing, fb_listing_id),
                }
            )

    def on_listing_filtered(listing):
        if cancelled.is_set():
            return
        fb_listing_id = _next_fb_listing_id()
        filtered_count_holder[0] += 1
        if debug_mode:
            event_queue.put(
                {
                    "type": "debug_facebook_listing",
                    "listing": build_debug_listing_dict(
                        listing,
                        fb_listing_id,
                        filtered=True,
                    ),
                }
            )

    def listing_passes_filter(listing) -> bool:
        """Return True if the listing should be kept (not suspicious)."""
        return not is_suspicious_price(listing.price)

    def on_inspector_url(url: str):
        if not cancelled.is_set():
            event_queue.put({"type": _EVENT_INSPECTOR_URL, "url": url, "source": "fb"})

    def scrape_worker():
        auth_failed = False
        try:
            if cancelled.is_set():
                return
            search_fb_marketplace(
                query=request.query,
                zip_code=request.zipCode,
                radius=request.radius,
                max_listings=request.maxListings,
                headless=not debug_mode,
                on_listing_found=on_listing_found,
                on_listing_filtered=on_listing_filtered,
                listing_filter=listing_passes_filter,
                extract_descriptions=request.extractDescriptions,
                step_sep=None,
                on_inspector_url=on_inspector_url if debug_mode else None,
                cancelled=cancelled,
            )
        except SearchCancelledError:
            return
        except FacebookNotLoggedInError:
            auth_failed = True
            if not cancelled.is_set():
                logger.warning("🔒 Facebook session expired — notifying client")
                event_queue.put({"type": "auth_error"})
        except LocationNotFoundError as e:
            if not cancelled.is_set():
                logger.warning(f"⚠️ {e}")
                event_queue.put({"type": "location_error", "message": str(e)})
                cancelled.set()
        except Exception as e:
            if not cancelled.is_set():
                log_error_short(logger, f"Step 2 failed: {e}")
        finally:
            if not cancelled.is_set() and not auth_failed:
                event_queue.put({"type": "scrape_done"})

    def event_generator():
        nonlocal cancelled

        def drain_log_queue():
            """Yield any debug_log, progress, and inspector_url events in the queue (non-blocking)."""
            while True:
                try:
                    ev = event_queue.get_nowait()
                except queue.Empty:
                    return
                if ev.get("type") in ("debug_log", "progress", _EVENT_INSPECTOR_URL):
                    yield f"data: {json.dumps(ev)}\n\n"

        thread_id: Optional[int] = None
        ebay_pool_ref: list[Optional[EbayScraperPool]] = [None]

        def _force_close_ebay_pool() -> None:
            pool = ebay_pool_ref[0]
            if pool:
                pool.force_close_all()

        try:
            location_info_stream = request.zipCode
            log_step_sep(logger, f"🔍 Step 1: Starting search — query='{request.query}', location={location_info_stream}, radius={request.radius}mi")
            log_step_sep(logger, "📜 Step 2: Scraping Facebook Marketplace")
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'scraping'})}\n\n"
            if debug_mode:
                debug_mode_payload = {
                    "type": "debug_mode",
                    "debug": True,
                    "query": request.query,
                    "zipCode": request.zipCode,
                    "radius": request.radius,
                    "maxListings": request.maxListings,
                    "threshold": request.threshold,
                    "extractDescriptions": request.extractDescriptions,
                }
                yield f"data: {json.dumps(debug_mode_payload)}\n\n"

            thread = threading.Thread(target=scrape_worker)
            thread.start()
            thread_id = thread.ident

            set_active_search(cancelled=cancelled, thread_id=thread_id)

            while True:
                try:
                    event = event_queue.get(timeout=0.5)

                    if event["type"] == "auth_error":
                        logger.warning("🔒 Sending auth_error to client")
                        yield f"data: {json.dumps({'type': 'auth_error'})}\n\n"
                        return
                    
                    if event["type"] == "location_error":
                        logger.warning("⚠️ Sending location_error to client")
                        yield f"data: {json.dumps({'type': 'location_error', 'message': event.get('message', 'Location not found')})}\n\n"
                        return

                    if event["type"] == "scrape_done":
                        break

                    try:
                        yield f"data: {json.dumps(event)}\n\n"
                    except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        cancelled.set()
                        force_close_active_scraper(thread_id)
                        raise
                except queue.Empty:
                    if cancelled.is_set():
                        force_close_active_scraper(thread_id)
                        break
                    continue

            yield from drain_log_queue()

            if not cancelled.is_set():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    log_warning(logger, "Scraping thread still running after join timeout")
            else:
                thread.join(timeout=2.0)

            if cancelled.is_set():
                return

            yield from drain_log_queue()

            filtered_count = filtered_count_holder[0]
            logger.info(
                f"📋 Found {len(fb_evaluable_listings)} listings"
                + (f" ({filtered_count} filtered out)" if filtered_count > 0 else "")
            )
            if filtered_count > 0:
                yield f"data: {json.dumps({'type': 'filtered', 'filteredCount': filtered_count})}\n\n"
            yield from drain_log_queue()
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'evaluating'})}\n\n"

            def evaluation_worker():
                scored = []
                count = 0
                if not fb_evaluable_listings:
                    log_warning(logger, "Step 2: No listings found - login may be required")
                    event_queue.put({"type": "evaluation_done", "scored_listings": scored, "evaluated_count": count})
                    return
                worker_count = max(1, LISTING_EVAL_MAX_WORKERS)
                log_step_sep(
                    logger,
                    f"📊 Step 3: Processing {len(fb_evaluable_listings)} FB listings ({worker_count} workers)",
                )

                def on_ebay_inspector_url(url: str):
                    if not cancelled.is_set():
                        event_queue.put({"type": _EVENT_INSPECTOR_URL, "url": url, "source": "ebay"})

                market_price_cache = {}
                market_price_cache_lock = threading.Lock()
                scored_by_index = {}

                ebay_pool = EbayScraperPool(
                    size=worker_count,
                    headless=not debug_mode,
                    cancelled=cancelled,
                    on_inspector_url=on_ebay_inspector_url if debug_mode else None,
                )
                ebay_pool_ref[0] = ebay_pool

                def evaluate_listing(index: int, fb_listing_id: str, listing):
                    """
                    Evaluate one FB listing using a pooled eBay browser.

                    Acquires an idle browser from the pool, runs the comparison, then
                    releases it back for the next task. Uses a shared per-search eBay
                    price cache so repeated queries reuse sold-item stats.
                    """
                    worker_thread_id = threading.get_ident()
                    listing_label = f"[{index}/{len(fb_evaluable_listings)}] FB listing: {listing.title}"
                    if debug_mode:
                        event_queue.put({
                            "type": "debug_ebay_query_start",
                            "listingIndex": index,
                            "fbListingId": fb_listing_id,
                            "fbTitle": listing.title,
                        })
                    if debug_log_handler is not None:
                        debug_log_handler.start_thread_buffer(worker_thread_id, listing_label)

                    ebay_scraper = ebay_pool.acquire()
                    try:
                        def on_query_generated(ebay_query: str):
                            if debug_mode and not cancelled.is_set():
                                event_queue.put({
                                    "type": "debug_ebay_query_generated",
                                    "listingIndex": index,
                                    "fbListingId": fb_listing_id,
                                    "fbTitle": listing.title,
                                    "ebayQuery": ebay_query,
                                })

                        result = compare_listing_to_ebay(
                            listing=listing,
                            original_query=request.query,
                            threshold=request.threshold,
                            n_items=DEFAULT_EBAY_ITEMS,
                            listing_index=index,
                            total_listings=len(fb_evaluable_listings),
                            cancelled=cancelled,
                            ebay_scraper=ebay_scraper,
                            market_price_cache=market_price_cache,
                            market_price_cache_lock=market_price_cache_lock,
                            on_query_generated=on_query_generated,
                        )
                        if debug_log_handler is not None:
                            debug_log_handler.finish_thread_buffer(worker_thread_id, "done")
                        return index, fb_listing_id, listing, result
                    except SearchCancelledError:
                        if debug_log_handler is not None:
                            debug_log_handler.finish_thread_buffer(worker_thread_id, "cancelled")
                        raise
                    except Exception:
                        if debug_log_handler is not None:
                            debug_log_handler.finish_thread_buffer(worker_thread_id, "failed")
                        raise
                    finally:
                        ebay_pool.release(ebay_scraper)

                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                        future_to_input = {}
                        total_listings = len(fb_evaluable_listings)
                        for idx, (fb_listing_id, listing) in enumerate(fb_evaluable_listings, 1):
                            if cancelled.is_set():
                                break
                            future = executor.submit(evaluate_listing, idx, fb_listing_id, listing)
                            future_to_input[future] = (idx, fb_listing_id, listing)
                            if LISTING_EVAL_WORKER_START_DELAY_SEC > 0 and idx < total_listings:
                                time.sleep(LISTING_EVAL_WORKER_START_DELAY_SEC)

                        pending = set(future_to_input.keys())
                        while pending:
                            if cancelled.is_set():
                                for future in pending:
                                    future.cancel()
                                _force_close_ebay_pool()
                                break

                            done, pending = concurrent.futures.wait(
                                pending,
                                timeout=EVAL_WAIT_TIMEOUT_SEC,
                                return_when=concurrent.futures.FIRST_COMPLETED,
                            )

                            for future in done:
                                idx, fb_listing_id, listing = future_to_input[future]
                                try:
                                    completed_index, completed_fb_listing_id, completed_listing, result = future.result()
                                    count += 1
                                    if debug_mode:
                                        event_queue.put({
                                            "type": "debug_ebay_query_finished",
                                            "listingIndex": completed_index,
                                            "fbListingId": completed_fb_listing_id,
                                            "failed": False,
                                        })
                                    if result:
                                        scored_by_index[completed_index] = result
                                        event_queue.put({
                                            "type": "listing_result",
                                            "listing": result,
                                            "listingIndex": completed_index,
                                            "fbListingId": completed_fb_listing_id,
                                            "evaluatedCount": count,
                                        })
                                    else:
                                        event_queue.put({
                                            "type": "listing_processed",
                                            "listingIndex": completed_index,
                                            "fbListingId": completed_fb_listing_id,
                                            "evaluatedCount": count,
                                            "currentListing": completed_listing.title,
                                        })
                                except SearchCancelledError:
                                    if cancelled.is_set():
                                        continue
                                    if debug_mode:
                                        event_queue.put({
                                            "type": "debug_ebay_query_finished",
                                            "listingIndex": idx,
                                            "fbListingId": fb_listing_id,
                                            "failed": True,
                                        })
                                    cancelled.set()
                                    for pending_future in pending:
                                        pending_future.cancel()
                                    _force_close_ebay_pool()
                                except Exception as e:
                                    if cancelled.is_set():
                                        continue
                                    if debug_mode:
                                        event_queue.put({
                                            "type": "debug_ebay_query_finished",
                                            "listingIndex": idx,
                                            "fbListingId": fb_listing_id,
                                            "failed": True,
                                        })
                                    log_warning(logger, f"Error processing listing '{listing.title}': {e}")
                                    count += 1
                                    error_result = {
                                        "title": listing.title,
                                        "price": listing.price,
                                        "currency": listing.currency,
                                        "location": listing.location,
                                        "url": listing.url,
                                        "dealScore": None,
                                        "noCompReason": "Unable to generate eBay comparisons",
                                    }
                                    scored_by_index[idx] = error_result
                                    event_queue.put({
                                        "type": "listing_result",
                                        "listing": error_result,
                                        "listingIndex": idx,
                                        "fbListingId": fb_listing_id,
                                        "evaluatedCount": count,
                                    })
                finally:
                    ebay_pool.close_all()
                    scored = [scored_by_index[i] for i in sorted(scored_by_index)]
                event_queue.put({
                    "type": "evaluation_done",
                    "scored_listings": scored,
                    "evaluated_count": count,
                })

            eval_thread = threading.Thread(target=evaluation_worker)
            eval_thread.start()

            while True:
                if cancelled.is_set():
                    _force_close_ebay_pool()
                    return
                try:
                    event = event_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if event["type"] == "evaluation_done":
                    scored_listings = event["scored_listings"]
                    evaluated_count = event["evaluated_count"]
                    break
                if event["type"] == "debug_ebay_query_generated":
                    yield f"data: {json.dumps(event)}\n\n"
                    continue
                if event["type"] == "debug_ebay_query_start":
                    yield f"data: {json.dumps(event)}\n\n"
                    continue
                if event["type"] == "debug_ebay_query_finished":
                    yield f"data: {json.dumps(event)}\n\n"
                    continue
                if event["type"] == "listing_result":
                    yield f"data: {json.dumps(event)}\n\n"
                    continue
                if event["type"] == "listing_processed":
                    yield f"data: {json.dumps(event)}\n\n"
                    continue
                if event.get("type") in ("debug_log", "progress", _EVENT_INSPECTOR_URL):
                    yield f"data: {json.dumps(event)}\n\n"

            eval_thread.join(timeout=2.0)
            if cancelled.is_set():
                _force_close_ebay_pool()
                return
            total_scanned = len(fb_evaluable_listings) + filtered_count
            log_step_sep(logger, f"✅ Step 4: Search completed — {total_scanned} scanned, {filtered_count} filtered, {len(scored_listings)} deals found")
            yield from drain_log_queue()
            done_event = {
                "type": "done",
                "scannedCount": total_scanned,
                "filteredCount": filtered_count,
                "evaluatedCount": evaluated_count,
                "listings": scored_listings,
                "threshold": request.threshold,
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            cancelled.set()
            if thread_id is not None:
                force_close_active_scraper(thread_id)
            _force_close_ebay_pool()
            raise
        except Exception as e:
            log_error_short(logger, f"Error in event generator: {e}")
            cancelled.set()
            raise
        finally:
            if debug_log_handler is not None:
                for name in _DEBUG_LOG_LOGGER_NAMES:
                    try:
                        logging.getLogger(name).removeHandler(debug_log_handler)
                    except Exception:
                        pass
            mark_search_complete()

    return event_generator()
