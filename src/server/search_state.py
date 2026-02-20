"""
Active search state, cancellation, and Chrome cleanup.

Manages the global state for the currently running search so that a cancel
request from a separate HTTP call can immediately kill Chrome and stop work.
Also provides a safety-net helper that kills lingering Chrome processes.
"""

import glob
import os
import signal
import threading

from src.scrapers.fb_marketplace_scraper import (
    force_close_active_scraper,
    CHROME_DEBUG_PORT as FB_CHROME_DEBUG_PORT,
)
from src.scrapers.ebay_scraper_v2 import EBAY_CHROME_DEBUG_PORT
from src.utils.search_runtime_config import LISTING_EVAL_MAX_WORKERS

_EBAY_CHROME_PORTS = [
    EBAY_CHROME_DEBUG_PORT + i for i in range(LISTING_EVAL_MAX_WORKERS)
]
_CHROME_DEBUG_PORTS = [FB_CHROME_DEBUG_PORT] + _EBAY_CHROME_PORTS
_CHROME_USER_DATA_DIRS = ["/tmp/chrome-fb"] + [
    f"/tmp/chrome-ebay-{port}" for port in _EBAY_CHROME_PORTS
]
_PREVIOUS_SEARCH_CLEANUP_TIMEOUT = 10.0

# Active search state for immediate cancellation from a separate HTTP request.
# "complete" is set when a search finishes all cleanup; new searches wait on it.
# Poison pill sent to the event queue so the generator unblocks immediately on cancel.
CANCEL_SIGNAL_TYPE = "_cancel_signal"
_CANCEL_SIGNAL = {"type": CANCEL_SIGNAL_TYPE}

_active_search: dict = {
    "cancelled": None,
    "thread_id": None,
    "event_queue": None,
    "complete": threading.Event(),
}
_active_search["complete"].set()
_active_search_lock = threading.Lock()


def _signal_cancellation():
    """Read the active search state and kill Chrome for the FB scraper thread.

    Puts a poison pill in the event queue so the generator unblocks immediately
    instead of waiting up to 0.5s in event_queue.get(). eBay pool cleanup is
    handled by the event generator via ebay_pool_ref.
    Returns the complete event so callers can optionally wait on it.
    """
    with _active_search_lock:
        cancelled = _active_search.get("cancelled")
        thread_id = _active_search.get("thread_id")
        event_queue = _active_search.get("event_queue")
        complete = _active_search["complete"]

    if cancelled is not None:
        cancelled.set()
    if event_queue is not None:
        try:
            event_queue.put_nowait(_CANCEL_SIGNAL)
        except Exception:
            # Queue is unbounded; put_nowait should not raise. Ignore defensively.
            pass
    if thread_id is not None:
        force_close_active_scraper(thread_id)

    return complete


def cancel_and_wait_for_previous_search():
    """Cancel any running search and block until its cleanup is fully done.

    Sets the cancelled flag on the active search, kills Chrome processes for
    both scraper threads, then waits for the event_generator's finally block
    to signal completion. Called at the start of every new search so the old
    one is guaranteed to be cleaned up before we launch new browsers.
    """
    complete = _signal_cancellation()
    complete.wait(timeout=_PREVIOUS_SEARCH_CLEANUP_TIMEOUT)


def cancel_active_search():
    """Cancel the currently running search immediately. Called from the cancel endpoint."""
    _signal_cancellation()


def set_active_search(*, cancelled, thread_id=None, event_queue=None):
    """Register the current search's cancellation event, thread ID, and event queue."""
    with _active_search_lock:
        _active_search["cancelled"] = cancelled
        if thread_id is not None:
            _active_search["thread_id"] = thread_id
        if event_queue is not None:
            _active_search["event_queue"] = event_queue


def mark_search_starting():
    """Mark a new search as starting (clear the complete event)."""
    with _active_search_lock:
        _active_search["complete"].clear()


def mark_search_complete():
    """Mark the current search as fully cleaned up."""
    with _active_search_lock:
        _active_search["cancelled"] = None
        _active_search["thread_id"] = None
        _active_search["event_queue"] = None
        _active_search["complete"].set()


def kill_lingering_chrome():
    """Kill any Chrome processes still using our debug ports and clean up lock files.

    Safety net for the rare case where normal cleanup didn't fully terminate Chrome
    (e.g. the process ignored SIGTERM, or cleanup timed out). Also removes Chrome's
    SingletonLock files so a fresh browser can start without "profile in use" errors.

    Scans /proc for processes launched with our specific --remote-debugging-port flags
    so it only targets our scrapers' Chrome instances, not unrelated processes.
    Pure Python — no external tools (fuser, lsof) needed in the container.
    """
    port_markers = [f"remote-debugging-port={p}" for p in _CHROME_DEBUG_PORTS]
    for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(cmdline_path, "rb") as f:
                cmdline = f.read().decode("utf-8", errors="replace")
            if any(marker in cmdline for marker in port_markers):
                pid = int(cmdline_path.split("/")[2])
                os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, ValueError, FileNotFoundError, PermissionError):
            pass

    for chrome_dir in _CHROME_USER_DATA_DIRS:
        lock_file = os.path.join(chrome_dir, "SingletonLock")
        try:
            os.remove(lock_file)
        except OSError:
            pass
