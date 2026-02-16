"""
eBay Sold Listings Scraper (v2)

Scrapes sold listings from eBay using Playwright. Uses its own Chrome process
(separate from the Facebook scraper — different ports, different browser session).
Stays open and is reused for multiple eBay searches per run. Sold listings determine market price.
"""

import json
import os
import statistics
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, List

from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

from src.scrapers.fb_marketplace_scraper import SearchCancelledError
from src.scrapers.utils import parse_price, random_delay
from src.utils.colored_logger import setup_colored_logger, log_warning
from src.utils.debug_chrome_proxy import start_debug_proxy

logger = setup_colored_logger("ebay_scraper_v2")

# Chrome ports for eBay (different from FB: 9222/9223) so both can run.
EBAY_CHROME_DEBUG_PORT = 9225
EBAY_PROXY_DEBUG_PORT = 9224
_INSPECTOR_URL_TEMPLATE = "http://localhost:{port}/devtools/inspector.html?ws=localhost:{port}/devtools/page/{page_id}"

# eBay sold search: LH_Sold=1 filters to sold items only.
EBAY_SOLD_SEARCH_BASE = "https://www.ebay.com/sch/i.html"

NAVIGATION_TIMEOUT_MS = 30000
ELEMENT_WAIT_TIMEOUT_MS = 20000

DEFAULT_EBAY_ITEMS = 25

# Full Chrome user-agent so eBay serves the standard desktop layout.
EBAY_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Listing card selectors — eBay uses su-card-container / s-card layout (updated 2026).
LISTING_CARD_SELECTOR = "div.su-card-container"
TITLE_SELECTOR = ".s-card__title"
PRICE_SELECTOR = ".s-card__price"
LINK_SELECTOR = "a[href*='/itm/']"
EXCLUDED_EXACT_LISTING_TITLES = {"Shop on eBay"}


@dataclass
class PriceStats:
    """Container for price statistics from sold listings."""
    search_term: str
    sample_size: int
    average: float
    raw_prices: list[float]
    item_summaries: Optional[List[dict]] = None


class EbaySoldScraper:
    """
    Scrapes sold eBay listings using Playwright. Creates one browser, reuses it
    for multiple searches. In headed mode, Chrome is visible for debugging.
    """

    def __init__(
        self,
        headless: bool = None,
        cancelled: Optional[threading.Event] = None,
        on_inspector_url: Optional[Callable[[str], None]] = None,
    ):
        if headless is None:
            self.headless = os.environ.get("DISPLAY") is None
        else:
            self.headless = headless
        
        self.cancelled = cancelled
        self._on_inspector_url = on_inspector_url
        self._is_closed = False
        self._chrome_process: Optional[subprocess.Popen] = None
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def _check_cancelled(self):
        """Raise if cancellation was requested. Call between Playwright operations."""
        if self.cancelled and self.cancelled.is_set():
            if not self._is_closed:
                self.close()
            raise SearchCancelledError("eBay search was cancelled by user")

    def _wait_for_chrome_debug_port(self, timeout: float = 15, poll_interval: float = 0.3):
        """Poll Chrome's debug endpoint until it responds or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._chrome_process and self._chrome_process.poll() is not None:
                raise RuntimeError(
                    f"Chrome exited unexpectedly with code {self._chrome_process.returncode}"
                )
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{EBAY_CHROME_DEBUG_PORT}/json/version", timeout=2
                ):
                    return
            except Exception:
                time.sleep(poll_interval)
        raise RuntimeError(
            f"Chrome debug port ({EBAY_CHROME_DEBUG_PORT}) did not respond within {timeout}s"
        )

    def _log_devtools_url(self):
        """Log the DevTools inspector URL when browser is created in headed mode."""
        fallback_url = f"http://localhost:{EBAY_PROXY_DEBUG_PORT}"
        try:
            with urllib.request.urlopen(
                f"http://localhost:{EBAY_CHROME_DEBUG_PORT}/json"
            ) as resp:
                pages = json.loads(resp.read())
            page = next((p for p in pages if p.get("url", "") != "about:blank"), None)
            if not page and pages:
                page = pages[0]
            if page:
                page_id = page.get("id", "")
                url = _INSPECTOR_URL_TEMPLATE.format(
                    port=EBAY_PROXY_DEBUG_PORT, page_id=page_id
                )
                logger.info(f"🌐 eBay browser inspect: {url}")
                if self._on_inspector_url:
                    self._on_inspector_url(url)
            else:
                logger.info(f"🌐 eBay browser live view: {fallback_url}")
                if self._on_inspector_url:
                    self._on_inspector_url(fallback_url)
        except Exception:
            logger.info(f"🌐 eBay browser live view: {fallback_url}")

    def _create_browser(self):
        """Create Playwright browser via subprocess, CDP connect, debug proxy in headed mode.

        Same pattern as FB scraper: subprocess Chrome so we can kill it on cancellation.
        Browser is reused for multiple searches; caller calls close() when done.
        """
        self._check_cancelled()
        if self._is_closed:
            self._is_closed = False

        self.playwright = sync_playwright().start()
        chrome_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--no-first-run",
            "--window-size=1920,1080",
            "--disable-gpu",
            "--disable-logging",
            "--log-level=3",
            "--user-data-dir=/tmp/chrome-ebay",
        ]
        self._check_cancelled()
        chrome_path = self.playwright.chromium.executable_path
        launch_args = [chrome_path]
        if self.headless:
            launch_args.append("--headless=new")
        launch_args.extend([
            f"--remote-debugging-port={EBAY_CHROME_DEBUG_PORT}",
            "--remote-allow-origins=*",
            *chrome_args,
            "about:blank",
        ])
        self._chrome_process = subprocess.Popen(
            launch_args,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )
        try:
            self._wait_for_chrome_debug_port()
        except RuntimeError as e:
            if self._chrome_process.poll() is not None:
                stderr = self._chrome_process.stderr
                extra = ""
                if stderr:
                    try:
                        err_text = stderr.read().decode("utf-8", errors="replace").strip()
                        if err_text:
                            extra = f" — Chrome output: {err_text[:500]}"
                    except Exception:
                        pass
                raise RuntimeError(str(e) + extra) from e
            raise
        self._check_cancelled()

        if not self.headless:
            start_debug_proxy(
                proxy_port=EBAY_PROXY_DEBUG_PORT,
                chrome_port=EBAY_CHROME_DEBUG_PORT,
            )

        self.browser = self.playwright.chromium.connect_over_cdp(
            f"http://localhost:{EBAY_CHROME_DEBUG_PORT}"
        )
        self._check_cancelled()
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=EBAY_USER_AGENT,
            locale="en-US",
            timezone_id="America/New_York",
        )
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        self._check_cancelled()
        self.page = self.context.new_page()
        self._check_cancelled()
        if not self.headless:
            self._log_devtools_url()

    def search_sold_listings(
        self, search_term: str, max_items: int = 50
    ) -> List[dict]:
        """
        Navigate to eBay sold search, extract listings, return [{title, price, url}, ...].
        Creates browser on first call; reuses for subsequent calls.
        """
        if not self.browser:
            self._create_browser()
        self._check_cancelled()

        params = {"_nkw": search_term, "LH_Sold": "1"}
        url = f"{EBAY_SOLD_SEARCH_BASE}?{urllib.parse.urlencode(params)}"
        self.page.goto(url, wait_until="load", timeout=NAVIGATION_TIMEOUT_MS)
        self._check_cancelled()
        random_delay(1.0, 2.0)

        try:
            self.page.wait_for_selector(
                LISTING_CARD_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT_MS, state="attached"
            )
        except Exception:
            logger.debug(f"eBay page URL after load: {self.page.url}")
            logger.debug(f"eBay page title: {self.page.title()}")
            log_warning(
                logger,
                "Could not find eBay listing cards — page layout may have changed",
            )
            return []
        self._check_cancelled()
        random_delay(0.5, 1.0)

        items: List[dict] = []
        cards = self.page.locator(LISTING_CARD_SELECTOR).all()
        for card in cards[:max_items]:
            self._check_cancelled()
            try:
                title_el = card.locator(TITLE_SELECTOR).first
                price_el = card.locator(PRICE_SELECTOR).first
                link_el = card.locator(LINK_SELECTOR).first
                title = title_el.text_content(timeout=3000) or ""
                price_text = price_el.text_content(timeout=3000) or ""
                href = link_el.get_attribute("href") or ""
            except Exception:
                continue
            price = parse_price(price_text)
            normalized_title = title.strip()
            if normalized_title in EXCLUDED_EXACT_LISTING_TITLES:
                continue
            if price is not None and price > 0 and normalized_title:
                items.append({"title": normalized_title, "price": price, "url": href})
        return items

    def get_sold_listing_stats(
        self, search_term: str, n_items: int = 50
    ) -> Optional[PriceStats]:
        """
        Scrape sold listings and return PriceStats (average, raw_prices, item_summaries).
        Returns None if no results or insufficient data.
        """
        items = self.search_sold_listings(search_term, max_items=n_items)
        if not items:
            log_warning(logger, f"No eBay sold results for '{search_term}'")
            return None
        prices = [i["price"] for i in items]
        item_summaries = [
            {"title": i["title"], "price": i["price"], "url": i["url"]}
            for i in items
        ]
        return PriceStats(
            search_term=search_term,
            sample_size=len(prices),
            average=statistics.mean(prices),
            raw_prices=sorted(prices),
            item_summaries=item_summaries,
        )

    def close(self):
        """Close browser and cleanup. Safe to call multiple times."""
        if self._is_closed:
            return
        self._is_closed = True
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_process.kill()
                self._chrome_process.wait(timeout=3)
            except Exception:
                pass
            self._chrome_process = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None


_active_ebay_scrapers: dict[int, EbaySoldScraper] = {}
_ebay_scraper_lock = threading.Lock()


def register_ebay_scraper(scraper: EbaySoldScraper) -> None:
    """Register scraper for the current thread (enables force_close on cancellation)."""
    with _ebay_scraper_lock:
        _active_ebay_scrapers[threading.get_ident()] = scraper


def unregister_ebay_scraper() -> None:
    """Unregister scraper for the current thread."""
    with _ebay_scraper_lock:
        _active_ebay_scrapers.pop(threading.get_ident(), None)


def force_close_active_ebay_scraper(thread_id: Optional[int] = None):
    """Kill Chrome for an active eBay scraper (e.g. on cancellation)."""
    if thread_id is None:
        thread_id = threading.get_ident()
    with _ebay_scraper_lock:
        scraper = _active_ebay_scrapers.get(thread_id)
        if scraper and scraper._chrome_process:
            try:
                scraper._chrome_process.kill()
            except Exception as e:
                log_warning(logger, f"Could not kill eBay Chrome process: {e}")


def force_close_all_active_ebay_scrapers():
    """Kill Chrome for all active eBay scrapers (used by parallel workers)."""
    with _ebay_scraper_lock:
        active_scrapers = list(_active_ebay_scrapers.values())

    for scraper in active_scrapers:
        if scraper and scraper._chrome_process:
            try:
                scraper._chrome_process.kill()
            except Exception as e:
                log_warning(logger, f"Could not kill eBay Chrome process: {e}")


def get_market_price(
    search_term: str,
    n_items: int = DEFAULT_EBAY_ITEMS,
    scraper: Optional[EbaySoldScraper] = None,
    headless: bool = None,
    cancelled: Optional[threading.Event] = None,
) -> Optional[PriceStats]:
    """
    Get average price from eBay sold listings. If scraper is provided, reuses it
    (caller must close when done). If not, creates a one-off scraper and closes after.
    """
    own_scraper = scraper is None
    if own_scraper:
        scraper = EbaySoldScraper(headless=headless, cancelled=cancelled)
    try:
        return scraper.get_sold_listing_stats(search_term, n_items)
    finally:
        if own_scraper:
            scraper.close()
