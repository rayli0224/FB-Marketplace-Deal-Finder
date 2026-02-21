"""
Runtime configuration for search/evaluation concurrency and pacing.

Centralizes environment-driven knobs for:
- parallel FB listing evaluation workers
- OpenAI post-filter batch concurrency and launch pacing
- cancellation polling intervals while waiting on concurrent tasks
"""

import os


def _read_positive_int_env(name: str, default: int) -> int:
    """Read a positive integer from env; fallback to default when invalid."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _read_non_negative_float_env(name: str, default: float) -> float:
    """Read a non-negative float from env; fallback to default when invalid."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if parsed >= 0 else default


# FB listing-level worker concurrency (search_stream.py)
LISTING_EVAL_MAX_WORKERS = _read_positive_int_env("LISTING_EVAL_MAX_WORKERS", 5)
LISTING_EVAL_WORKER_START_DELAY_SEC = _read_non_negative_float_env(
    "LISTING_EVAL_WORKER_START_DELAY_SEC",
    0.35,
)
EVAL_WAIT_TIMEOUT_SEC = _read_non_negative_float_env("EVAL_WAIT_TIMEOUT_SEC", 0.2)

# eBay post-filtering batch concurrency (ebay_results_filter/)
POST_FILTER_BATCH_SIZE = _read_positive_int_env("POST_FILTER_BATCH_SIZE", 10)
POST_FILTER_MAX_CONCURRENT_BATCHES = _read_positive_int_env(
    "POST_FILTER_MAX_CONCURRENT_BATCHES",
    5,
)
POST_FILTER_BATCH_START_DELAY_SEC = _read_non_negative_float_env(
    "POST_FILTER_BATCH_START_DELAY_SEC",
    0.35,
)
POST_FILTER_CANCEL_POLL_INTERVAL_SEC = _read_non_negative_float_env(
    "POST_FILTER_CANCEL_POLL_INTERVAL_SEC",
    0.2,
)

# OpenAI API concurrency control
OPENAI_MAX_CONCURRENT_REQUESTS = _read_positive_int_env("OPENAI_MAX_CONCURRENT_REQUESTS", 15)
