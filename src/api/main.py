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
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
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
    try:
        logger.info(f"Search request: query={request.query}, zip={request.zipCode}, radius={request.radius}")
        
        fb_listings = search_fb_marketplace(
            query=request.query,
            zip_code=request.zipCode,
            radius=request.radius,
            headless=True
        )
        
        scanned_count = len(fb_listings)
        logger.info(f"Found {scanned_count} Facebook Marketplace listings")
        
        ebay_stats = get_sold_item_stats(
            search_term=request.query,
            n_items=50,
            headless=True
        )
        
        if not ebay_stats:
            logger.warning("Could not get eBay price statistics")
            return SearchResponse(
                listings=[],
                scannedCount=scanned_count,
                evaluatedCount=0
            )
        
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
        
    except Exception as e:
        logger.error(f"Error during search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

