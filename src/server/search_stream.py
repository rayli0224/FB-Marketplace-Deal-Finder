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
    EbaySoldScraper,
    force_close_active_ebay_scraper,
    register_ebay_scraper,
    unregister_ebay_scraper,
)
from src.evaluation.listing_ebay_comparison import compare_listing_to_ebay
from src.evaluation.fb_listing_filter import is_suspicious_price
from src.utils.colored_logger import setup_colored_logger, log_step_sep, log_error_short, log_warning

from src.server.search_state import (
    cancel_and_wait_for_previous_search,
    kill_lingering_chrome,
    set_active_search,
    set_eval_thread_id,
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

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()
            if msg:
                self._event_queue.put({
                    "type": "debug_log",
                    "level": record.levelname,
                    "message": msg,
                })
        except Exception:
            pass


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
    fb_listings = []
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

    def build_debug_listing_dict(listing, filtered: bool = False) -> dict:
        """Build the dict payload for a debug_facebook_listing SSE event."""
        entry = {
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
        fb_listings.append(listing)
        event_queue.put({"type": "progress", "scannedCount": count})
        if debug_mode:
            event_queue.put({"type": "debug_facebook_listing", "listing": build_debug_listing_dict(listing)})

    def on_listing_filtered(listing):
        if cancelled.is_set():
            return
        filtered_count_holder[0] += 1
        if debug_mode:
            event_queue.put({"type": "debug_facebook_listing", "listing": build_debug_listing_dict(listing, filtered=True)})

    def listing_passes_filter(listing) -> bool:
        """Return True if the listing should be kept (not suspicious)."""
        return not is_suspicious_price(listing.price)

    def on_inspector_url(url: str):
        if not cancelled.is_set():
            event_queue.put({"type": _EVENT_INSPECTOR_URL, "url": url})

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
            logger.info(f"📋 Found {len(fb_listings)} listings" + (f" ({filtered_count} filtered out)" if filtered_count > 0 else ""))
            if filtered_count > 0:
                yield f"data: {json.dumps({'type': 'filtered', 'filteredCount': filtered_count})}\n\n"
            yield from drain_log_queue()
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'evaluating'})}\n\n"

            def evaluation_worker():
                scored = []
                count = 0
                if not fb_listings:
                    log_warning(logger, "Step 2: No listings found - login may be required")
                    event_queue.put({"type": "evaluation_done", "scored_listings": scored, "evaluated_count": count})
                    return
                log_step_sep(logger, f"📊 Step 3: Processing {len(fb_listings)} FB listings individually")

                def on_ebay_inspector_url(url: str):
                    if not cancelled.is_set():
                        event_queue.put({"type": _EVENT_INSPECTOR_URL, "url": url})

                ebay_scraper = EbaySoldScraper(
                    headless=not debug_mode,
                    cancelled=cancelled,
                    on_inspector_url=on_ebay_inspector_url if debug_mode else None,
                )
                register_ebay_scraper(ebay_scraper)
                try:
                    for idx, listing in enumerate(fb_listings, 1):
                        if cancelled.is_set():
                            break
                        try:
                            result = compare_listing_to_ebay(
                                listing=listing,
                                original_query=request.query,
                                threshold=request.threshold,
                                n_items=DEFAULT_EBAY_ITEMS,
                                listing_index=idx,
                                total_listings=len(fb_listings),
                                cancelled=cancelled,
                                ebay_scraper=ebay_scraper,
                            )
                            count += 1
                            if debug_mode and result and result.get("ebaySearchQuery"):
                                event_queue.put({
                                    "type": "debug_ebay_query",
                                    "fbTitle": listing.title,
                                    "ebayQuery": result["ebaySearchQuery"],
                                })
                            if result:
                                scored.append(result)
                                event_queue.put({
                                    "type": "listing_result",
                                    "listing": result,
                                    "evaluatedCount": count,
                                })
                            else:
                                event_queue.put({
                                    "type": "listing_processed",
                                    "evaluatedCount": count,
                                    "currentListing": listing.title,
                                })
                        except Exception as e:
                            if cancelled.is_set():
                                break
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
                            scored.append(error_result)
                            event_queue.put({
                                "type": "listing_result",
                                "listing": error_result,
                                "evaluatedCount": count,
                            })
                finally:
                    ebay_scraper.close()
                    unregister_ebay_scraper()
                event_queue.put({
                    "type": "evaluation_done",
                    "scored_listings": scored,
                    "evaluated_count": count,
                })

            eval_thread = threading.Thread(target=evaluation_worker)
            eval_thread.start()
            set_eval_thread_id(eval_thread.ident)

            while True:
                if cancelled.is_set():
                    force_close_active_ebay_scraper(eval_thread.ident)
                    return
                try:
                    event = event_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if event["type"] == "evaluation_done":
                    scored_listings = event["scored_listings"]
                    evaluated_count = event["evaluated_count"]
                    break
                if event["type"] == "debug_ebay_query":
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
                force_close_active_ebay_scraper(eval_thread.ident)
                return
            total_scanned = len(fb_listings) + filtered_count
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
            try:
                force_close_active_ebay_scraper(eval_thread.ident)
            except NameError:
                pass
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
