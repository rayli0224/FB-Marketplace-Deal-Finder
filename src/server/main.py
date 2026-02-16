"""
FastAPI HTTP server for FB Marketplace Deal Finder.

Defines the app, request/response models, and route handlers. Search orchestration
and SSE streaming live in search_stream.py; cancellation state in search_state.py.
"""

import json
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional

from src.scrapers.fb_marketplace_scraper import (
    search_marketplace as search_fb_marketplace,
    FacebookNotLoggedInError,
)
from src.scrapers.ebay_scraper_v2 import (
    get_market_price,
    DEFAULT_EBAY_ITEMS,
)
from src.evaluation.deal_calculator import score_listings
from src.utils.colored_logger import setup_colored_logger, log_step_sep, log_step_title, log_error_short, log_warning, wait_status

from src.server.search_state import cancel_active_search
from src.server.search_stream import create_search_stream

logger = setup_colored_logger("server")

RADIUS_OPTIONS = (1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500)
DEFAULT_RADIUS = 20

DEBUG_MODE = (
    os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    or "--debug" in sys.argv
)

app = FastAPI(title="FB Marketplace Deal Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

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
    filtered: bool = False


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


class SaveCookiesRequest(BaseModel):
    cookies: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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

    try:
        cookies = json.loads(request.cookies)
    except json.JSONDecodeError:
        return {"success": False, "error": "That doesn't look like valid login data. Make sure you copied the full export from the extension."}

    if not isinstance(cookies, list) or len(cookies) == 0:
        return {"success": False, "error": "The pasted data should be a list of entries. Try exporting again from the extension."}

    cookie_names = {c.get("name") for c in cookies if isinstance(c, dict)}
    if "c_user" not in cookie_names or "xs" not in cookie_names:
        return {
            "success": False,
            "error": "Missing essential Facebook login entries. Make sure you're exporting cookies while logged into facebook.com.",
        }

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
        log_warning(logger, "Step 2: No listings found - login may be required")
        return SearchResponse(listings=[], scannedCount=0, evaluatedCount=0)

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
        )
        evaluated_count = len(scored_listings)
        logger.info(f"✅ Found {evaluated_count} deals")
        log_step_sep(logger, f"✅ Step 5: Search completed — {scanned_count} scanned, {evaluated_count} deals found")
        return SearchResponse(
            listings=[ListingResponse(**listing) for listing in scored_listings],
            scannedCount=scanned_count,
            evaluatedCount=evaluated_count,
        )

    log_warning(logger, "No eBay stats — skipping deal scoring")
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
        evaluatedCount=len(all_listings),
    )


@app.post("/api/search/cancel")
def cancel_search():
    """Cancel the currently running search immediately. Called when the user clicks cancel."""
    cancel_active_search()
    return {"ok": True}


@app.post("/api/search/stream")
def search_deals_stream(request: SearchRequest):
    """
    Search Facebook Marketplace and stream real-time progress to the frontend.

    Launches FB scraping and per-listing eBay evaluation in background threads,
    streaming progress events via SSE. The heavy lifting lives in search_stream.py.
    """
    return StreamingResponse(
        create_search_stream(request, debug_mode=DEBUG_MODE),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
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

    return EbayStatsResponse(
        stats=EbayStats(
            searchTerm=stats.search_term,
            sampleSize=stats.sample_size,
            average=stats.average,
            rawPrices=stats.raw_prices,
        )
    )
