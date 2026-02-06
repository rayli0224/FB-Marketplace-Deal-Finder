"""
Database module for storing heist job results.

Uses SQLite to persist job results so they can be reviewed and dismissed
by users without being lost.
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Database file path (in project root)
DB_PATH = Path(__file__).parent.parent.parent / "heist_results.db"


def _get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the database schema if it doesn't exist."""
    conn = _get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS heist_jobs (
                job_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                radius INTEGER NOT NULL,
                threshold REAL NOT NULL,
                status TEXT NOT NULL,
                scanned_count INTEGER DEFAULT 0,
                evaluated_count INTEGER DEFAULT 0,
                results TEXT,  -- JSON blob of listings
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                dismissed BOOLEAN DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dismissed ON heist_jobs(dismissed)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON heist_jobs(created_at DESC)
        """)
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()


def save_job(job_id: str, query: str, zip_code: str, radius: int, threshold: float, status: str):
    """Save or update a job in the database."""
    conn = _get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO heist_jobs 
            (job_id, query, zip_code, radius, threshold, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job_id, query, zip_code, radius, threshold, status, datetime.utcnow()))
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving job {job_id}: {e}")
        raise
    finally:
        conn.close()


def update_job_results(job_id: str, status: str, scanned_count: int, evaluated_count: int, results: List[Dict[str, Any]]):
    """Update job with completion results."""
    conn = _get_connection()
    try:
        results_json = json.dumps(results) if results else None
        conn.execute("""
            UPDATE heist_jobs 
            SET status = ?, scanned_count = ?, evaluated_count = ?, results = ?, completed_at = ?
            WHERE job_id = ?
        """, (status, scanned_count, evaluated_count, results_json, datetime.utcnow(), job_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Error updating job results {job_id}: {e}")
        raise
    finally:
        conn.close()


def dismiss_job(job_id: str):
    """Mark a job as dismissed."""
    conn = _get_connection()
    try:
        conn.execute("""
            UPDATE heist_jobs 
            SET dismissed = 1 
            WHERE job_id = ?
        """, (job_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error dismissing job {job_id}: {e}")
        raise
    finally:
        conn.close()


def delete_job(job_id: str):
    """Permanently delete a job from the database."""
    conn = _get_connection()
    try:
        conn.execute("""
            DELETE FROM heist_jobs 
            WHERE job_id = ?
        """, (job_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        raise
    finally:
        conn.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single job by ID."""
    conn = _get_connection()
    try:
        row = conn.execute("""
            SELECT * FROM heist_jobs WHERE job_id = ?
        """, (job_id,)).fetchone()
        
        if not row:
            return None
        
        job = dict(row)
        if job['results']:
            job['results'] = json.loads(job['results'])
        return job
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        raise
    finally:
        conn.close()


def get_all_jobs(include_dismissed: bool = False) -> List[Dict[str, Any]]:
    """Get all jobs, optionally including dismissed ones."""
    conn = _get_connection()
    try:
        if include_dismissed:
            rows = conn.execute("""
                SELECT * FROM heist_jobs 
                ORDER BY created_at DESC
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM heist_jobs 
                WHERE dismissed = 0
                ORDER BY created_at DESC
            """).fetchall()
        
        jobs = []
        for row in rows:
            job = dict(row)
            if job['results']:
                job['results'] = json.loads(job['results'])
            jobs.append(job)
        
        return jobs
    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        raise
    finally:
        conn.close()
