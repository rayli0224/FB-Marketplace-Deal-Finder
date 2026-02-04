"""
FastAPI application for FB Marketplace Deal Finder.
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from src.scrapers.fb_marketplace_scraper import search_marketplace as search_fb_marketplace
from src.scrapers.ebay_scraper import get_sold_item_stats
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
        ebay_stats = get_sold_item_stats(
            search_term=request.query,
            n_items=50,
            headless=True
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

