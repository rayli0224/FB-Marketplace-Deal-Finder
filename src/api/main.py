"""
FastAPI application for FB Marketplace Deal Finder.
"""

import logging
import json
import queue
import threading
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from src.scrapers.fb_marketplace_scraper import search_marketplace as search_fb_marketplace
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import filter_and_score_listings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    radius: int = 25
    threshold: float = 20.0


class ListingResponse(BaseModel):
    title: str
    price: float
    location: str
    url: str
    dealScore: float


class SearchResponse(BaseModel):
    listings: List[ListingResponse]
    scannedCount: int
    evaluatedCount: int


class EbayStatsRequest(BaseModel):
    query: str
    nItems: int = 50


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


@app.post("/api/search", response_model=SearchResponse)
def search_deals(request: SearchRequest):
    """
    Search Facebook Marketplace and calculate deal scores using eBay market data.
    """
    logger.info(f"Search request: query={request.query}, zip={request.zipCode}, radius={request.radius}")
    
    # Try to scrape Facebook Marketplace
    fb_listings = []
    try:
        fb_listings = search_fb_marketplace(
            query=request.query,
            zip_code=request.zipCode,
            radius=request.radius,
            headless=True
        )
        logger.info(f"Found {len(fb_listings)} Facebook Marketplace listings")
    except Exception as e:
        logger.warning(f"FB Marketplace scraping failed (login may be required): {e}")
        # Continue without FB listings - will return empty results
    
    scanned_count = len(fb_listings)
    
    if scanned_count == 0:
        logger.warning("No FB Marketplace listings found. Facebook may require login.")
        return SearchResponse(
            listings=[],
            scannedCount=0,
            evaluatedCount=0
        )
    
    # Get eBay price statistics
    ebay_stats = None
    try:
        ebay_stats = get_market_price(
            search_term=request.query,
            n_items=50,
        )
    except Exception as e:
        logger.warning(f"eBay scraping failed: {e}")
    
    # If eBay stats available, filter by deal score
    if ebay_stats:
        scored_listings = filter_and_score_listings(
            fb_listings=fb_listings,
            ebay_stats=ebay_stats,
            threshold=request.threshold
        )
        evaluated_count = len(scored_listings)
        logger.info(f"Found {evaluated_count} deals above {request.threshold}% threshold")
        
        return SearchResponse(
            listings=[ListingResponse(**listing) for listing in scored_listings],
            scannedCount=scanned_count,
            evaluatedCount=evaluated_count
        )
    
    # No eBay stats - return all FB listings with dealScore=0 (unknown)
    logger.warning("No eBay stats - returning all FB listings without deal scoring")
    all_listings = [
        ListingResponse(
            title=listing.title,
            price=listing.price,
            location=listing.location,
            url=listing.url,
            dealScore=0.0,  # Unknown deal score
        )
        for listing in fb_listings
    ]
    
    return SearchResponse(
        listings=all_listings,
        scannedCount=scanned_count,
        evaluatedCount=len(all_listings)
    )


@app.post("/api/search/stream")
def search_deals_stream(request: SearchRequest):
    """
    Search Facebook Marketplace and stream real-time progress to the frontend.
    
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
    """
    event_queue = queue.Queue()
    fb_listings = []
    
    def on_listing_found(listing, count):
        fb_listings.append(listing)
        event_queue.put({"type": "progress", "scannedCount": count})
    
    def scrape_worker():
        try:
            search_fb_marketplace(
                query=request.query,
                zip_code=request.zipCode,
                radius=request.radius,
                headless=True,
                on_listing_found=on_listing_found
            )
        except Exception as e:
            logger.warning(f"FB Marketplace scraping failed: {e}")
        event_queue.put({"type": "scrape_done"})
    
    def event_generator():
        # Phase 1: Scraping Facebook
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'scraping'})}\n\n"
        
        thread = threading.Thread(target=scrape_worker)
        thread.start()
        
        # Stream progress events
        while True:
            event = event_queue.get()
            if event["type"] == "scrape_done":
                break
            yield f"data: {json.dumps(event)}\n\n"
        
        thread.join()
        
        # Phase 2: Fetching eBay prices
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'ebay'})}\n\n"
        
        scored_listings = []
        if fb_listings:
            try:
                ebay_stats = get_market_price(
                    search_term=request.query,
                    n_items=50,
                )
                
                # Phase 3: Calculating deals
                yield f"data: {json.dumps({'type': 'phase', 'phase': 'calculating'})}\n\n"
                
                if ebay_stats:
                    scored_listings = filter_and_score_listings(
                        fb_listings=fb_listings,
                        ebay_stats=ebay_stats,
                        threshold=request.threshold
                    )
            except Exception as e:
                logger.warning(f"eBay scraping failed: {e}")
        
        # Send completion event
        done_event = {
            "type": "done",
            "scannedCount": len(fb_listings),
            "evaluatedCount": len(scored_listings),
            "listings": scored_listings
        }
        yield f"data: {json.dumps(done_event)}\n\n"
    
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
    logger.info(f"eBay test request: query={request.query}, nItems={request.nItems}")

    try:
        stats = get_market_price(
            search_term=request.query,
            n_items=request.nItems,
        )
    except Exception as e:
        logger.error(f"eBay test scraping failed: {e}")
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
