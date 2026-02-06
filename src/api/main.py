"""
FastAPI application for FB Marketplace Deal Finder.
"""

import logging
import json
import queue
import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict

from src.scrapers.fb_marketplace_scraper import search_marketplace as search_fb_marketplace
from src.scrapers.ebay_scraper import get_market_price
from src.api.deal_calculator import filter_and_score_listings
from src.api.database import (
    init_database,
    save_job,
    update_job_results,
    dismiss_job,
    delete_job,
    get_job,
    get_all_jobs as get_all_jobs_from_db
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database on startup
init_database()


class SearchRequest(BaseModel):
    query: str
    zipCode: str
    radius: int = 25
    threshold: float = 20.0


class JobStatus(str, Enum):
    """Status of a heist job in the queue."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class HeistJob:
    """Represents a queued heist request."""
    job_id: str
    request: SearchRequest
    event_queue: queue.Queue
    status: JobStatus = JobStatus.PENDING


# Global queue and job tracking
MAX_QUEUE_SIZE = 10
heist_queue: queue.Queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
active_jobs: Dict[str, HeistJob] = {}
jobs_lock = threading.Lock()

# Persistent scraper instance for reuse across jobs
persistent_scraper = None
scraper_lock = threading.Lock()


def _get_or_create_scraper():
    """Get or create a persistent scraper instance for reuse across jobs."""
    global persistent_scraper
    with scraper_lock:
        if persistent_scraper is None:
            from src.scrapers.fb_marketplace_scraper import FBMarketplaceScraper
            persistent_scraper = FBMarketplaceScraper(headless=True)
            logger.info("Created persistent browser instance for heist queue")
        return persistent_scraper


def _process_heist_job(job: HeistJob):
    """Process a single heist job: scrape FB, fetch eBay prices, calculate deals."""
    with jobs_lock:
        job.status = JobStatus.PROCESSING
    
    # Save job status to database
    save_job(
        job_id=job.job_id,
        query=job.request.query,
        zip_code=job.request.zipCode,
        radius=job.request.radius,
        threshold=job.request.threshold,
        status=JobStatus.PROCESSING.value
    )
    
    fb_listings = []
    
    def on_listing_found(listing, count):
        fb_listings.append(listing)
        job.event_queue.put({"type": "progress", "scannedCount": count})
    
    try:
        scraper = _get_or_create_scraper()
        job.event_queue.put({"type": "phase", "phase": "scraping"})
        
        scraper.search_marketplace(
            query=job.request.query,
            zip_code=job.request.zipCode,
            radius=job.request.radius,
            on_listing_found=on_listing_found
        )
        
        job.event_queue.put({"type": "phase", "phase": "ebay"})
        ebay_stats = get_market_price(search_term=job.request.query, n_items=50)
        
        job.event_queue.put({"type": "phase", "phase": "calculating"})
        scored_listings = []
        if ebay_stats and fb_listings:
            scored_listings = filter_and_score_listings(
                fb_listings=fb_listings,
                ebay_stats=ebay_stats,
                threshold=job.request.threshold
            )
        
        # Save results to database (scored_listings is already a list of dicts)
        update_job_results(
            job_id=job.job_id,
            status=JobStatus.COMPLETED.value,
            scanned_count=len(fb_listings),
            evaluated_count=len(scored_listings),
            results=scored_listings
        )
        
        done_event = {
            "type": "done",
            "scannedCount": len(fb_listings),
            "evaluatedCount": len(scored_listings),
            "listings": scored_listings
        }
        job.event_queue.put(done_event)
        
        with jobs_lock:
            job.status = JobStatus.COMPLETED
            
    except Exception as e:
        logger.error(f"Heist job {job.job_id} failed: {e}")
        job.event_queue.put({"type": "error", "message": str(e)})
        
        # Save failure status to database
        update_job_results(
            job_id=job.job_id,
            status=JobStatus.FAILED.value,
            scanned_count=len(fb_listings),
            evaluated_count=0,
            results=[]
        )
        
        with jobs_lock:
            job.status = JobStatus.FAILED


def _heist_worker():
    """Background worker that processes heist jobs from the queue."""
    logger.info("Heist worker thread started")
    while True:
        try:
            job = heist_queue.get()
            logger.info(f"Processing heist job {job.job_id}")
            _process_heist_job(job)
            heist_queue.task_done()
        except Exception as e:
            logger.error(f"Error in heist worker: {e}")


# Start the background worker thread
worker_thread = threading.Thread(target=_heist_worker, daemon=True)
worker_thread.start()
logger.info("Heist queue worker thread started")

app = FastAPI(title="FB Marketplace Deal Finder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class QueueStatusResponse(BaseModel):
    """Response model for queue status."""
    queueSize: int
    maxQueueSize: int
    activeJobs: int


class JobStatusResponse(BaseModel):
    """Response model for individual job status."""
    jobId: str
    status: str
    query: Optional[str] = None
    zipCode: Optional[str] = None


class JobResponse(BaseModel):
    """Response model for a job with full details."""
    jobId: str
    query: str
    zipCode: str
    radius: int
    threshold: float
    status: str
    scannedCount: int
    evaluatedCount: int
    results: Optional[List[ListingResponse]] = None
    createdAt: str
    completedAt: Optional[str] = None
    dismissed: bool


class JobsListResponse(BaseModel):
    """Response model for list of jobs."""
    jobs: List[JobResponse]


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
    Queue a heist job and stream real-time progress to the frontend.
    
    Jobs are processed asynchronously by a background worker thread, allowing
    multiple heists to be queued. The browser instance is reused across jobs
    for efficiency.
    
    How it works:
    1. Create a job with unique ID and add it to the queue
    2. Return job ID and queue position immediately
    3. Stream events as the job progresses through the queue
    4. Worker processes jobs sequentially, reusing browser instance
    """
    job_id = str(uuid.uuid4())
    event_queue = queue.Queue()
    job = HeistJob(job_id=job_id, request=request, event_queue=event_queue)
    
    # Try to add job to queue (non-blocking)
    try:
        # Calculate position before adding (qsize + 1 = position of new job)
        queue_position = heist_queue.qsize() + 1
        heist_queue.put(job, block=False)
        logger.info(f"Job {job_id} queued at position {queue_position}")
    except queue.Full:
        return StreamingResponse(
            content=json.dumps({
                "type": "error",
                "message": f"Queue is full (max {MAX_QUEUE_SIZE} jobs). Please try again later."
            }),
            media_type="application/json",
            status_code=503
        )
    
    # Save job to database
    save_job(
        job_id=job_id,
        query=request.query,
        zip_code=request.zipCode,
        radius=request.radius,
        threshold=request.threshold,
        status=JobStatus.PENDING.value
    )
    
    # Store job in active_jobs for tracking
    with jobs_lock:
        active_jobs[job_id] = job
    
    def event_generator():
        # Send initial status with job ID and queue position
        yield f"data: {json.dumps({'type': 'queued', 'jobId': job_id, 'queuePosition': queue_position})}\n\n"
        
        # Wait for job to start processing (status changes from PENDING to PROCESSING)
        import time
        while job.status == JobStatus.PENDING:
            # Queue size includes this job, so position is approximately qsize()
            # But ensure it's at least 1 (next to be processed)
            current_queue_size = heist_queue.qsize()
            current_position = max(1, current_queue_size)
            yield f"data: {json.dumps({'type': 'waiting', 'queuePosition': current_position})}\n\n"
            time.sleep(0.5)
        
        # Stream events from job's event queue
        while True:
            try:
                event = job.event_queue.get(timeout=1.0)
                yield f"data: {json.dumps(event)}\n\n"
                
                # Stop streaming when job is done or failed
                if event.get("type") in ("done", "error"):
                    break
            except queue.Empty:
                # Check if job completed while waiting
                with jobs_lock:
                    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                        break
                continue
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@app.get("/api/queue/status", response_model=QueueStatusResponse)
def get_queue_status():
    """Get the current status of the heist queue."""
    with jobs_lock:
        active_count = len([j for j in active_jobs.values() if j.status != JobStatus.COMPLETED])
    
    return QueueStatusResponse(
        queueSize=heist_queue.qsize(),
        maxQueueSize=MAX_QUEUE_SIZE,
        activeJobs=active_count
    )


@app.get("/api/queue/job/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    """Get the status of a specific heist job."""
    with jobs_lock:
        job = active_jobs.get(job_id)
    
    if not job:
        # Try database
        db_job = get_job(job_id)
        if not db_job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobStatusResponse(
            jobId=db_job['job_id'],
            status=db_job['status'],
            query=db_job['query'],
            zipCode=db_job['zip_code']
        )
    
    return JobStatusResponse(
        jobId=job.job_id,
        status=job.status.value,
        query=job.request.query,
        zipCode=job.request.zipCode
    )


@app.get("/api/jobs", response_model=JobsListResponse)
def get_all_jobs(include_dismissed: bool = False):
    """Get all jobs, optionally including dismissed ones."""
    db_jobs = get_all_jobs_from_db(include_dismissed=include_dismissed)
    
    jobs = []
    for db_job in db_jobs:
        job_response = JobResponse(
            jobId=db_job['job_id'],
            query=db_job['query'],
            zipCode=db_job['zip_code'],
            radius=db_job['radius'],
            threshold=db_job['threshold'],
            status=db_job['status'],
            scannedCount=db_job['scanned_count'],
            evaluatedCount=db_job['evaluated_count'],
            results=[ListingResponse(**listing) for listing in db_job['results']] if db_job['results'] else None,
            createdAt=db_job['created_at'],
            completedAt=db_job['completed_at'],
            dismissed=bool(db_job['dismissed'])
        )
        jobs.append(job_response)
    
    return JobsListResponse(jobs=jobs)


@app.post("/api/jobs/{job_id}/dismiss")
def dismiss_job_endpoint(job_id: str):
    """Dismiss a job so it no longer appears in the active jobs list."""
    db_job = get_job(job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    dismiss_job(job_id)
    return {"message": f"Job {job_id} dismissed"}


@app.delete("/api/jobs/{job_id}")
def delete_job_endpoint(job_id: str):
    """Permanently delete a job from the database."""
    db_job = get_job(job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    delete_job(job_id)
    
    # Also remove from active_jobs if present
    with jobs_lock:
        active_jobs.pop(job_id, None)
    
    return {"message": f"Job {job_id} deleted"}
    
    
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
