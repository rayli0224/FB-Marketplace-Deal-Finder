"""
FastAPI application for FB Marketplace Deal Finder.
"""

import json
import logging
import os
import queue
import sys
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional

# Supported radius values in miles (must match Facebook Marketplace location dialog).
RADIUS_OPTIONS = (1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500)
DEFAULT_RADIUS = 20

from src.scrapers.fb_marketplace_scraper import search_marketplace as search_fb_marketplace, FacebookNotLoggedInError, SearchCancelledError, force_close_active_scraper
from src.scrapers.ebay_scraper import get_market_price, DEFAULT_EBAY_ITEMS
from src.api.deal_calculator import score_listings
from src.utils.listing_processor import process_single_listing
from src.utils.colored_logger import setup_colored_logger, log_step_sep, log_step_title, log_error_short, wait_status

logger = setup_colored_logger("api")

# Active search state for immediate cancellation from a separate HTTP request.
_active_search: dict = {"cancelled": None, "thread_id": None}
_active_search_lock = threading.Lock()


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


DEBUG_MODE = (
    os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    or "--debug" in sys.argv
)

# Loggers that receive the queue handler in debug mode (they use propagate=False).
_DEBUG_LOG_LOGGER_NAMES = ("api", "fb_scraper", "listing_processor", "openai_helpers", "ebay_scraper")

# SSE event types for the search stream.
_EVENT_INSPECTOR_URL = "inspector_url"

app = FastAPI(title="FB Marketplace Deal Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    zipCode: str
    radius: int = DEFAULT_RADIUS
    threshold: float
    maxListings: int = 20
    extractDescriptions: bool = False

    @field_validator("radius")
    @classmethod
    def radius_must_be_supported(cls, v: int) -> int:
        if v not in RADIUS_OPTIONS:
            raise ValueError(
                "Radius must be one of: 1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500"
            )
        return v


class CompItemSummary(BaseModel):
    """Single eBay comp listing for transparency UI."""
    title: str
    price: float
    url: str
    filtered: bool = False  # True if this item was filtered out as non-comparable


class ListingResponse(BaseModel):
    title: str
    price: float
    location: str
    url: str
    dealScore: Optional[float] = None
    ebaySearchQuery: Optional[str] = None
    compPrice: Optional[float] = None
    compPrices: Optional[List[float]] = None
    compItems: Optional[List[CompItemSummary]] = None
    noCompReason: Optional[str] = None


class SearchResponse(BaseModel):
    listings: List[ListingResponse]
    scannedCount: int
    evaluatedCount: int


class EbayStatsRequest(BaseModel):
    query: str
    nItems: int = DEFAULT_EBAY_ITEMS


class EbayStats(BaseModel):
    searchTerm: str
    sampleSize: int
    average: float
    rawPrices: List[float]


class EbayStatsResponse(BaseModel):
    stats: Optional[EbayStats]


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/cookies/status")
def cookies_status():
    """
    Check whether Facebook login data is configured and looks valid.

    Reads the cookies file path from the FB_COOKIES_FILE env var (or the default),
    parses it as JSON, and checks for the two essential Facebook session cookies
    (c_user and xs). Returns a status object the frontend can use to decide whether
    to show the search form or the cookie setup screen.
    """
    cookies_file = os.environ.get("FB_COOKIES_FILE", "/app/cookies/facebook_cookies.json")

    if not os.path.exists(cookies_file):
        return {"configured": False, "reason": "no_file"}

    try:
        with open(cookies_file, "r") as f:
            cookies = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"configured": False, "reason": "invalid_file"}

    if not isinstance(cookies, list) or len(cookies) == 0:
        return {"configured": False, "reason": "empty"}

    cookie_names = {c.get("name") for c in cookies if isinstance(c, dict)}
    has_critical = "c_user" in cookie_names and "xs" in cookie_names

    if not has_critical:
        return {"configured": False, "reason": "missing_critical_cookies"}

    return {"configured": True}


class SaveCookiesRequest(BaseModel):
    cookies: str  # Raw JSON string pasted by the user


@app.post("/api/cookies")
def save_cookies(request: SaveCookiesRequest):
    """
    Accept pasted Facebook login data from the frontend and save it to disk.

    Parses the raw JSON string the user pasted from a cookie-export browser extension,
    validates that it's a non-empty array containing the two essential Facebook session
    cookies (c_user and xs), then writes the file to the configured cookies path.
    Returns success or a descriptive error the frontend can display.
    """
    cookies_file = os.environ.get("FB_COOKIES_FILE", "/app/cookies/facebook_cookies.json")

    # Parse the pasted JSON
    try:
        cookies = json.loads(request.cookies)
    except json.JSONDecodeError:
        return {"success": False, "error": "That doesn't look like valid login data. Make sure you copied the full export from the extension."}

    if not isinstance(cookies, list) or len(cookies) == 0:
        return {"success": False, "error": "The pasted data should be a list of entries. Try exporting again from the extension."}

    # Validate critical cookies are present
    cookie_names = {c.get("name") for c in cookies if isinstance(c, dict)}
    if "c_user" not in cookie_names or "xs" not in cookie_names:
        return {
            "success": False,
            "error": "Missing essential Facebook login entries. Make sure you're exporting cookies while logged into facebook.com.",
        }

    # Ensure directory exists and write the file
    try:
        os.makedirs(os.path.dirname(cookies_file), exist_ok=True)
        with open(cookies_file, "w") as f:
            json.dump(cookies, f, indent=2)
        logger.info(f"✅ Facebook login data saved ({len(cookies)} entries)")
        return {"success": True}
    except Exception as e:
        log_error_short(logger, f"Failed to save cookies: {e}")
        return {"success": False, "error": "Couldn't save login data. Please try again."}


@app.post("/api/search", response_model=SearchResponse)
def search_deals(request: SearchRequest):
    """
    Search Facebook Marketplace and calculate deal scores using eBay market data.
    """
    log_step_sep(logger, f"🔍 Step 1: Starting search — query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
    log_step_sep(logger, "📜 Step 2: Scraping Facebook Marketplace")
    fb_listings = []
    try:
        fb_listings = search_fb_marketplace(
            query=request.query,
            zip_code=request.zipCode,
            radius=request.radius,
            max_listings=request.maxListings,
            headless=not DEBUG_MODE,
            extract_descriptions=request.extractDescriptions,
            step_sep="sub",
        )
        logger.info(f"📋 Found {len(fb_listings)} listings")
    except FacebookNotLoggedInError:
        logger.warning("🔒 Facebook session expired during non-streaming search")
        return JSONResponse(
            status_code=401,
            content={"error": "auth_error", "message": "Facebook session expired"}
        )
    except Exception as e:
        log_error_short(logger, f"Step 2 failed: {e}")
    scanned_count = len(fb_listings)
    if scanned_count == 0:
        logger.warning("⚠️ Step 2: No listings found - login may be required")
        return SearchResponse(
            listings=[],
            scannedCount=0,
            evaluatedCount=0
        )

    log_step_sep(logger, "💰 Step 3: Fetching eBay prices")
    ebay_stats = None
    try:
        with wait_status(logger, "eBay prices"):
            ebay_stats = get_market_price(
                search_term=request.query,
                n_items=DEFAULT_EBAY_ITEMS,
            )
    except Exception as e:
        log_error_short(logger, f"Step 3 failed: {e}")
    if ebay_stats:
        log_step_sep(logger, "📊 Step 4: Calculating deal scores")
        scored_listings = score_listings(
            fb_listings=fb_listings,
            ebay_stats=ebay_stats,
            threshold=request.threshold
        )
        evaluated_count = len(scored_listings)
        logger.info(f"✅ Found {evaluated_count} deals")
        log_step_sep(logger, f"✅ Step 5: Search completed — {scanned_count} scanned, {evaluated_count} deals found")
        return SearchResponse(
            listings=[ListingResponse(**listing) for listing in scored_listings],
            scannedCount=scanned_count,
            evaluatedCount=evaluated_count
        )
    
    logger.warning("No eBay stats — skipping deal scoring")
    all_listings = [
        ListingResponse(
            title=listing.title,
            price=listing.price,
            location=listing.location,
            url=listing.url,
            dealScore=None,
            noCompReason="eBay prices unavailable",
        )
        for listing in fb_listings
    ]
    log_step_sep(logger, f"✅ Step 5: Search completed — {scanned_count} scanned, {len(all_listings)} returned")
    return SearchResponse(
        listings=all_listings,
        scannedCount=scanned_count,
        evaluatedCount=len(all_listings)
    )


@app.post("/api/search/cancel")
def cancel_search():
    """Cancel the currently running search immediately. Called when the user clicks cancel."""
    with _active_search_lock:
        cancelled = _active_search.get("cancelled")
        thread_id = _active_search.get("thread_id")
    if cancelled is not None:
        cancelled.set()
    if thread_id is not None:
        force_close_active_scraper(thread_id)
    return {"ok": True}


@app.post("/api/search/stream")
def search_deals_stream(request: SearchRequest):
    """
    Search Facebook Marketplace and stream real-time progress to the frontend.
    
    Note: This endpoint processes listings individually, making OpenAI and eBay API calls
    for each FB listing found. This can be slow but provides accurate per-listing comparisons.
    
    This endpoint allows the frontend to show a live counter of listings found,
    rather than waiting for the entire search to complete before showing results.
    
    How it works:
    1. Frontend connects to this endpoint using EventSource (Server-Sent Events)
    2. As each Facebook listing is found, we send a progress event: {"type": "progress", "scannedCount": N}
    3. After all listings are found, we fetch eBay prices and calculate deal scores
    4. Finally, we send a completion event with all results: {"type": "done", "listings": [...], ...}
    
    Technical note: We use a background thread for scraping because the scraper uses
    a callback for each listing found, but SSE requires a generator. A queue bridges
    the two: the callback pushes events to the queue, the generator reads from it.
    
    Cancellation: When the client disconnects, the generator detects it and signals
    cancellation to stop all processing (scraping thread and listing evaluation).
    """
    event_queue = queue.Queue()
    fb_listings = []
    cancelled = threading.Event()

    debug_log_handler = None
    if DEBUG_MODE:
        debug_log_handler = QueueLogHandler(event_queue)
        debug_log_handler.setLevel(logging.DEBUG)
        for name in _DEBUG_LOG_LOGGER_NAMES:
            logging.getLogger(name).addHandler(debug_log_handler)

    log_step_sep(logger, f"Search request — query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
    
    def on_listing_found(listing, count):
        if cancelled.is_set():
            return
        fb_listings.append(listing)
        event_queue.put({"type": "progress", "scannedCount": count})

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
                headless=not DEBUG_MODE,
                on_listing_found=on_listing_found,
                extract_descriptions=request.extractDescriptions,
                step_sep=None,
                on_inspector_url=on_inspector_url if DEBUG_MODE else None,
                cancelled=cancelled,
            )
        except SearchCancelledError:
            return
        except FacebookNotLoggedInError:
            auth_failed = True
            if not cancelled.is_set():
                logger.warning("🔒 Facebook session expired — notifying client")
                event_queue.put({"type": "auth_error"})
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
            log_step_sep(logger, f"🔍 Step 1: Starting search — query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
            log_step_sep(logger, "📜 Step 2: Scraping Facebook Marketplace")
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'scraping'})}\n\n"
            if DEBUG_MODE:
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

            with _active_search_lock:
                _active_search["cancelled"] = cancelled
                _active_search["thread_id"] = thread_id

            # Stream progress events with timeout to check for cancellation
            while True:
                # Check for cancellation first, even if queue has items
                if cancelled.is_set():
                    force_close_active_scraper(thread_id)
                    break
                
                try:
                    # Use timeout to periodically check if cancelled
                    event = event_queue.get(timeout=0.5)
                    
                    # Check cancellation again after getting event (cancellation may have happened while waiting)
                    if cancelled.is_set():
                        force_close_active_scraper(thread_id)
                        break
                    
                    if event["type"] == "auth_error":
                        logger.warning("🔒 Sending auth_error to client")
                        yield f"data: {json.dumps({'type': 'auth_error'})}\n\n"
                        return

                    if event["type"] == "scrape_done":
                        break

                    # debug_log and progress events are yielded so the frontend can display them
                    # Check cancellation before yielding (client may have disconnected)
                    if cancelled.is_set():
                        force_close_active_scraper(thread_id)
                        break

                    try:
                        yield f"data: {json.dumps(event)}\n\n"
                    except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        cancelled.set()
                        # Force close browser immediately for the scraping thread
                        force_close_active_scraper(thread_id)
                        raise
                except queue.Empty:
                    # Queue is empty, continue loop to check cancellation again
                    continue

            yield from drain_log_queue()

            # Wait for thread to finish, but don't block forever if cancelled
            if not cancelled.is_set():
                thread.join(timeout=1.0)
                if thread.is_alive():
                    logger.warning("⚠️ Scraping thread still running after join timeout")
            else:
                # Give thread a moment to check cancelled flag and exit
                thread.join(timeout=2.0)
            
            if cancelled.is_set():
                return

            yield from drain_log_queue()

            logger.info(f"📋 Found {len(fb_listings)} listings")
            yield from drain_log_queue()
            if DEBUG_MODE:
                debug_facebook_payload = [
                    {
                        "title": listing.title,
                        "price": listing.price,
                        "location": listing.location,
                        "url": listing.url,
                        "description": listing.description or "",
                    }
                    for listing in fb_listings
                ]
                yield f"data: {json.dumps({'type': 'debug_facebook', 'listings': debug_facebook_payload})}\n\n"
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'evaluating'})}\n\n"

            def evaluation_worker():
                scored = []
                count = 0
                if not fb_listings:
                    logger.warning("⚠️ Step 2: No listings found - login may be required")
                    event_queue.put({"type": "evaluation_done", "scored_listings": scored, "evaluated_count": count})
                    return
                log_step_sep(logger, f"📊 Step 3: Processing {len(fb_listings)} FB listings individually")
                for idx, listing in enumerate(fb_listings, 1):
                    if cancelled.is_set():
                        break
                    try:
                        result = process_single_listing(
                            listing=listing,
                            original_query=request.query,
                            threshold=request.threshold,
                            n_items=DEFAULT_EBAY_ITEMS,
                            listing_index=idx,
                            total_listings=len(fb_listings),
                            cancelled=cancelled,
                        )
                        count += 1
                        if DEBUG_MODE and result and result.get("ebaySearchQuery"):
                            event_queue.put({
                                "type": "debug_ebay_query",
                                "fbTitle": listing.title,
                                "ebayQuery": result["ebaySearchQuery"],
                            })
                        # Send the full listing result for incremental display
                        if result:
                            scored.append(result)
                            event_queue.put({
                                "type": "listing_result",
                                "listing": result,
                                "evaluatedCount": count,
                            })
                        else:
                            # No result (e.g., filtered out) - still send progress
                            event_queue.put({
                                "type": "listing_processed",
                                "evaluatedCount": count,
                                "currentListing": listing.title,
                            })
                    except Exception as e:
                        if cancelled.is_set():
                            break
                        logger.warning(f"Error processing listing '{listing.title}': {e}")
                        count += 1
                        error_result = {
                            "title": listing.title,
                            "price": listing.price,
                            "location": listing.location,
                            "url": listing.url,
                            "dealScore": None,
                            "noCompReason": "Unable to generate eBay comparisons",
                        }
                        scored.append(error_result)
                        # Send the error result for incremental display
                        event_queue.put({
                            "type": "listing_result",
                            "listing": error_result,
                            "evaluatedCount": count,
                        })
                event_queue.put({
                    "type": "evaluation_done",
                    "scored_listings": scored,
                    "evaluated_count": count,
                })

            eval_thread = threading.Thread(target=evaluation_worker)
            eval_thread.start()

            while True:
                if cancelled.is_set():
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
                if event.get("type") in ("debug_log", "progress"):
                    yield f"data: {json.dumps(event)}\n\n"

            eval_thread.join(timeout=2.0)
            if cancelled.is_set():
                return
            log_step_sep(logger, f"✅ Step 4: Search completed — {len(fb_listings)} scanned, {len(scored_listings)} deals found")
            yield from drain_log_queue()
            done_event = {
                "type": "done",
                "scannedCount": len(fb_listings),
                "evaluatedCount": evaluated_count,
                "listings": scored_listings,
                "threshold": request.threshold,
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        except (GeneratorExit, BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            cancelled.set()
            if thread_id is not None:
                force_close_active_scraper(thread_id)
            raise
        except Exception as e:
            # Other errors - still signal cancellation to stop background work
            log_error_short(logger, f"Error in event generator: {e}")
            cancelled.set()
            raise
        finally:
            with _active_search_lock:
                _active_search["cancelled"] = None
                _active_search["thread_id"] = None
            if debug_log_handler is not None:
                for name in _DEBUG_LOG_LOGGER_NAMES:
                    try:
                        logging.getLogger(name).removeHandler(debug_log_handler)
                    except Exception:
                        pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
    
    
@app.post("/api/ebay", response_model=EbayStatsResponse)
def ebay_active_listings(request: EbayStatsRequest):
    """
    Directly call the eBay active listings API.
    Returns average price from active listings.
    """
    log_step_title(logger, f"▶️ Step 1: eBay test request - query='{request.query}', nItems={request.nItems}")

    try:
        with wait_status(logger, "eBay test"):
            stats = get_market_price(
                search_term=request.query,
                n_items=request.nItems,
            )
        log_step_title(logger, f"✅ Step 2: eBay test completed - {stats.sample_size if stats else 0} items analyzed")
    except Exception as e:
        log_error_short(logger, f"Step 2 failed: {e}")
        return EbayStatsResponse(stats=None)

    if not stats:
        return EbayStatsResponse(stats=None)
    else:
        return EbayStatsResponse(
            stats=EbayStats(
                searchTerm=stats.search_term,
                sampleSize=stats.sample_size,
                average=stats.average,
                rawPrices=stats.raw_prices,
            )
        )
