"""
FastAPI application for FB Marketplace Deal Finder.
"""

import logging
import json
import queue
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from src.scrapers.fb_marketplace_scraper import search_marketplace as search_fb_marketplace
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import score_listings
from src.utils.listing_processor import process_single_listing
from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix
logger = setup_colored_logger("api", level=logging.INFO)

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
    threshold: float


class ListingResponse(BaseModel):
    title: str
    price: float
    location: str
    url: str
    dealScore: Optional[float]


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
    logger.info(f"▶️  Step 1: Starting search - query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
    
    # Try to scrape Facebook Marketplace
    logger.info("▶️  Step 2: Scraping Facebook Marketplace")
    fb_listings = []
    try:
        fb_listings = search_fb_marketplace(
            query=request.query,
            zip_code=request.zipCode,
            radius=request.radius,
            headless=True
        )
        logger.info(f"✅ Step 2 complete: Found {len(fb_listings)} listings")
    except Exception as e:
        logger.error(f"❌ Step 2 failed: {str(e)[:100]}")
        # Continue without FB listings - will return empty results
    
    scanned_count = len(fb_listings)
    
    if scanned_count == 0:
        logger.warning("⚠️  Step 2: No listings found - login may be required")
        return SearchResponse(
            listings=[],
            scannedCount=0,
            evaluatedCount=0
        )
    
    # Get eBay price statistics
    logger.info("▶️  Step 3: Fetching eBay prices")
    ebay_stats = None
    try:
        ebay_stats = get_market_price(
            search_term=request.query,
            n_items=50,
        )
    except Exception as e:
        logger.error(f"❌ Step 3 failed: {str(e)[:100]}")
    
    # If eBay stats available, filter listings by price threshold and score them
    if ebay_stats:
        logger.info("▶️  Step 4: Calculating deal scores")
        scored_listings = score_listings(
            fb_listings=fb_listings,
            ebay_stats=ebay_stats,
            threshold=request.threshold
        )
        evaluated_count = len(scored_listings)
        logger.info(f"✅ Step 4 complete: Found {evaluated_count} deals")
        logger.info(f"{'='*60}")
        logger.info(f"🎯 Step 5: Search completed - {scanned_count} scanned, {evaluated_count} deals found")
        logger.info(f"{'='*60}")
        
        return SearchResponse(
            listings=[ListingResponse(**listing) for listing in scored_listings],
            scannedCount=scanned_count,
            evaluatedCount=evaluated_count
        )
    
    logger.warning("⚠️  Step 3: No eBay stats available - skipping deal scoring")
    all_listings = [
        ListingResponse(
            title=listing.title,
            price=listing.price,
            location=listing.location,
            url=listing.url,
            dealScore=None,
        )
        for listing in fb_listings
    ]
    
    logger.info(f"{'='*60}")
    logger.info(f"🎯 Step 5: Search completed - {scanned_count} scanned, {len(all_listings)} returned")
    logger.info(f"{'='*60}")
    return SearchResponse(
        listings=all_listings,
        scannedCount=scanned_count,
        evaluatedCount=len(all_listings)
    )


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
    """
    logger.info(f"🔍 Received search request: query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
    
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
            logger.error(f"❌ Step 2 failed: {str(e)[:100]}")
        event_queue.put({"type": "scrape_done"})
    
    def event_generator():
        logger.info(f"▶️  Step 1: Starting search - query='{request.query}', zip={request.zipCode}, radius={request.radius}mi")
        
        # Phase 1: Scraping Facebook
        logger.info("▶️  Step 2: Scraping Facebook Marketplace")
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
        logger.info(f"✅ Step 2 complete: Found {len(fb_listings)} listings")
        
        # Phase 2: Processing each listing individually
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'evaluating'})}\n\n"
        
        scored_listings = []
        evaluated_count = 0
        
        if fb_listings:
            logger.info("")
            logger.info("╔" + "═" * 78 + "╗")
            logger.info(f"║  Processing {len(fb_listings)} FB listings individually...")
            logger.info("╚" + "═" * 78 + "╝")
            logger.info("")
            
            for idx, listing in enumerate(fb_listings, 1):
                try:
                    # Process single listing: OpenAI → eBay → deal score
                    result = process_single_listing(
                        listing=listing,
                        original_query=request.query,
                        threshold=request.threshold,
                        n_items=50,
                        listing_index=idx,
                        total_listings=len(fb_listings)
                    )
                    
                    evaluated_count += 1
                    
                    # Stream progress after each listing is processed
                    yield f"data: {json.dumps({
                        'type': 'listing_processed',
                        'evaluatedCount': evaluated_count,
                        'currentListing': listing.title
                    })}\n\n"
                    
                    # If listing meets threshold, add to results
                    if result:
                        scored_listings.append(result)
                        # Deal found logging is handled in listing_processor.py
                        
                except Exception as e:
                    logger.warning(f"Error processing listing '{listing.title}': {e}")
                    evaluated_count += 1
                    # Stream progress even if processing failed
                    yield f"data: {json.dumps({
                        'type': 'listing_processed',
                        'evaluatedCount': evaluated_count,
                        'currentListing': listing.title
                    })}\n\n"
        else:
            logger.warning("⚠️  Step 2: No listings found - login may be required")
        
        # Send completion event
        logger.info(f"{'='*60}")
        logger.info(f"🎯 Step 5: Search completed - {len(fb_listings)} scanned, {len(scored_listings)} deals found")
        logger.info(f"{'='*60}")
        done_event = {
            "type": "done",
            "scannedCount": len(fb_listings),
            "evaluatedCount": evaluated_count,
            "listings": scored_listings,
            "threshold": request.threshold
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
    logger.info(f"▶️  Step 1: eBay test request - query='{request.query}', nItems={request.nItems}")

    try:
        stats = get_market_price(
            search_term=request.query,
            n_items=request.nItems,
        )
        logger.info(f"✅ Step 2: eBay test completed - {stats.sample_size if stats else 0} items analyzed")
    except Exception as e:
        logger.error(f"❌ Step 2 failed: {str(e)[:100]}")
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
