"""
Facebook Marketplace Scraper

Scrapes Facebook Marketplace listings using Playwright for better anti-detection.
Supports searching by query, zip code, and radius.

Authentication is handled by the app: users provide login data via the in-app setup,
which is stored and loaded from the path in FB_COOKIES_FILE. The scraper expects
that file to contain a JSON array of cookie objects (e.g. name, value, domain, path).
"""

import re
import os
import json
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, List, Callable
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError
from src.scrapers.utils import random_delay, parse_price, is_valid_listing_price
from src.utils.colored_logger import setup_colored_logger, log_data_block, log_listing_box_sep, set_step_indent, clear_step_indent, wait_status
from src.utils.debug_chrome_proxy import start_debug_proxy

logger = setup_colored_logger("fb_scraper")

# Default cookie file path
COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "/app/cookies/facebook_cookies.json")

# Chrome remote debugging ports (used in headed/debug mode).
# Chrome listens on CHROME_DEBUG_PORT (localhost only); the TCP proxy in
# debug_chrome_proxy forwards PROXY_DEBUG_PORT (0.0.0.0) → CHROME_DEBUG_PORT
# so Docker port forwarding can reach it from the host machine.
CHROME_DEBUG_PORT = 9223
PROXY_DEBUG_PORT = 9222

# Timeouts: prevent hanging when an element is missing or the page is stuck; fail after this long.
NAVIGATION_TIMEOUT_MS = 20000
ELEMENT_WAIT_TIMEOUT_MS = 8000
ACTION_TIMEOUT_MS = 4000

# Results area: wait for this after search page loads.
SEARCH_RESULTS_SELECTOR = "div[role='main']"

# DevTools inspector URL template (used when logging and for the open-in-browser callback).
_INSPECTOR_URL_TEMPLATE = "http://localhost:{port}/devtools/inspector.html?ws=localhost:{port}/devtools/page/{page_id}"

# Facebook Marketplace location dialog: one selector per target (no fallbacks).
LOCATION_PILL_SELECTOR = "span:has-text('Within')"
LOCATION_INPUT_SELECTOR = "input[aria-label='Location']"
LOCATION_DIALOG_SELECTOR = "[role='dialog']"
LOCATION_APPLY_SELECTOR = "[aria-label='Apply'][role='button']"

# Price extraction selectors (shared across methods)
PRICE_SELECTORS = [
    "span[class*='price']",
    "div[class*='price']",
    "span:has-text('$')",
]

# Location fallback values
LOCATION_UNKNOWN = "Unknown"
LOCATION_SHIPPED = "Shipped"

# Description extraction constants
DESCRIPTION_MAX_LINES = 50
DESCRIPTION_MIN_LENGTH = 10
DESCRIPTION_SIBLING_CHECK_COUNT = 3
SCROLL_ATTEMPTS = 3


class FacebookNotLoggedInError(Exception):
    """
    Raised when the scraper detects that the Facebook session is invalid or expired.

    This happens when navigating to Marketplace results in a redirect to the login page
    or when login-wall elements are visible on the page, indicating the saved login data
    is no longer valid and needs to be re-exported.
    """
    pass


@dataclass
class Listing:
    title: str
    price: float
    location: str
    url: str
    description: str = ""
    
    def __str__(self) -> str:
        return f"Listing(title='{self.title}', price=${self.price:.2f}, location='{self.location}', url='{self.url}')"


class FBMarketplaceScraper:
    
    MARKETPLACE_SEARCH_URL = "https://www.facebook.com/marketplace/search"
    
    def __init__(self, headless: bool = None, cookies_file: str = None):
        """
        Initialize the Facebook Marketplace scraper. Loads cookies from JSON file.
        """
        if headless is None:
            self.headless = os.environ.get("DISPLAY") is None
        else:
            self.headless = headless
        
        self.cookies_file = cookies_file or COOKIES_FILE
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._chrome_process: Optional[subprocess.Popen] = None
    
    def _load_cookies(self) -> List[dict]:
        """Load cookies from JSON file."""
        if not os.path.exists(self.cookies_file):
            return []
        
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            # Convert cookies to Playwright format if needed
            playwright_cookies = []
            for cookie in cookies:
                pc = {
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain", ".facebook.com"),
                    "path": cookie.get("path", "/"),
                }
                # Optional fields
                if "expires" in cookie or "expirationDate" in cookie:
                    pc["expires"] = cookie.get("expires") or cookie.get("expirationDate", -1)
                if "httpOnly" in cookie:
                    pc["httpOnly"] = cookie.get("httpOnly", False)
                if "secure" in cookie:
                    pc["secure"] = cookie.get("secure", True)
                if "sameSite" in cookie:
                    # Playwright expects "Strict", "Lax", or "None"
                    ss = cookie.get("sameSite", "None")
                    if isinstance(ss, str):
                        pc["sameSite"] = ss.capitalize() if ss.lower() in ["strict", "lax", "none"] else "None"
                
                playwright_cookies.append(pc)
            
            return playwright_cookies
            
        except (json.JSONDecodeError, Exception):
            return []
    
    def _wait_for_chrome_debug_port(self, timeout: float = 15, poll_interval: float = 0.3):
        """Poll Chrome's debug endpoint until it responds or the timeout expires.

        Raises RuntimeError if Chrome exits before the endpoint is ready, or if
        the timeout is reached without a successful connection.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Check the process hasn't crashed
            if self._chrome_process and self._chrome_process.poll() is not None:
                raise RuntimeError(
                    f"Chrome exited unexpectedly with code {self._chrome_process.returncode} "
                    "before the debug port was ready"
                )
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{CHROME_DEBUG_PORT}/json/version", timeout=2
                ):
                    return
            except Exception:
                time.sleep(poll_interval)
        raise RuntimeError(
            f"Chrome debug port ({CHROME_DEBUG_PORT}) did not respond within {timeout}s"
        )

    def _log_devtools_url(self, on_inspector_url: Optional[Callable[[str], None]] = None):
        """Log the DevTools inspector URL and optionally invoke a callback with it.

        Queries Chrome's debug endpoint for the list of open pages, picks the first
        one, and builds the inspector URL. Logs it and calls on_inspector_url if
        provided (e.g. so the frontend can open it in the user's browser).
        """
        fallback_url = f"http://localhost:{PROXY_DEBUG_PORT}"
        try:
            with urllib.request.urlopen(f"http://localhost:{CHROME_DEBUG_PORT}/json") as resp:
                pages = json.loads(resp.read())
            page = next((p for p in pages if p.get("url", "") != "about:blank"), None)
            if not page and pages:
                page = pages[0]
            if page:
                page_id = page.get("id", "")
                url = _INSPECTOR_URL_TEMPLATE.format(port=PROXY_DEBUG_PORT, page_id=page_id)
                logger.info(f"🌐 Inspect browser: {url}")
                if on_inspector_url:
                    on_inspector_url(url)
            else:
                logger.info(f"🌐 Browser live view: {fallback_url}")
        except Exception:
            logger.info(f"🌐 Browser live view: {fallback_url}")

    def _create_browser(self):
        """Create a Playwright browser with stealth settings and load cookies.

        In headed mode (debug), launches Chromium manually with a remote debugging
        port so you can view the browser live at http://localhost:9222 from your
        host machine. Playwright connects to it via CDP instead of launching its
        own instance (which would use a pipe and block the debugging port).
        """
        self.playwright = sync_playwright().start()

        chrome_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--window-size=1920,1080",
        ]

        if not self.headless:
            chrome_path = self.playwright.chromium.executable_path
            self._chrome_process = subprocess.Popen([
                chrome_path,
                f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                "--remote-allow-origins=*",
                *chrome_args,
                "about:blank",
            ])
            self._wait_for_chrome_debug_port()
            start_debug_proxy()
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{CHROME_DEBUG_PORT}")
        else:
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=chrome_args,
            )
        
        self.context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # Load cookies for authentication
        cookies = self._load_cookies()
        if cookies:
            self.context.add_cookies(cookies)
        
        self.page = self.context.new_page()
        
        if not self.headless:
            on_inspector_url = getattr(self, "_on_inspector_url", None)
            self._log_devtools_url(on_inspector_url=on_inspector_url)
    
    def _check_logged_in(self):
        """
        Check whether the browser is logged into Facebook after navigating to Marketplace.

        Inspects the current URL and page content for signs of being redirected to a login
        page. Facebook redirects unauthenticated users to /login or shows a login form when
        session cookies are missing or expired. Raises FacebookNotLoggedInError if any
        login-wall signal is detected.
        """
        current_url = self.page.url.lower()

        # Facebook redirects logged-out users to /login or /checkpoint
        if "/login" in current_url or "/checkpoint" in current_url:
            logger.warning("🔒 Detected login redirect — Facebook session is invalid")
            raise FacebookNotLoggedInError("Facebook session expired or invalid")

        # Check for login form (single selector: if present, we're on a login wall)
        login_form = self.page.locator("form[action*='login']").first
        if login_form.is_visible(timeout=500):
            logger.warning("🔒 Detected login form — Facebook session is invalid")
            raise FacebookNotLoggedInError("Facebook session expired or invalid")

    def _goto_search_results(self, query: str):
        """Navigate directly to Marketplace search results URL, verify login, and wait for results.

        Bypasses the homepage and search bar; the query is in the URL so we land on results
        immediately and can set location without waiting for the search bar to render.
        """
        url = f"{self.MARKETPLACE_SEARCH_URL}?query={urllib.parse.quote(query)}"
        self.page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        self._check_logged_in()
        self.page.wait_for_selector(SEARCH_RESULTS_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT_MS)

    def _set_location(self, zip_code: str, radius: int):
        """Open the location dialog, set zip code and radius, then apply the filters.

        Opens the location dialog by clicking the location pill, sets the radius dropdown
        first (while the dialog is fresh and fully interactive), then fills the zip code
        input and selects the first autocomplete suggestion. Finally clicks Apply and waits
        for the search results to reload with the new filters applied.
        """
        try:
            location_pill = self.page.locator(LOCATION_PILL_SELECTOR).first
            location_pill.click(timeout=ACTION_TIMEOUT_MS)
            random_delay(0.5, 1)

            self._set_radius(radius)
            random_delay(0.3, 0.6)

            location_input = self.page.locator(LOCATION_INPUT_SELECTOR).first
            location_input.fill(zip_code, timeout=ACTION_TIMEOUT_MS)
            random_delay(0.4, 0.8)
            location_input.press("ArrowDown")
            random_delay(0.2, 0.4)
            location_input.press("Enter")
            random_delay(0.5, 1)

            apply_button = self.page.locator(LOCATION_APPLY_SELECTOR).first
            apply_button.click(timeout=ACTION_TIMEOUT_MS)

            random_delay(2, 3)
            self.page.wait_for_selector(SEARCH_RESULTS_SELECTOR, timeout=ELEMENT_WAIT_TIMEOUT_MS)

        except FacebookNotLoggedInError:
            raise
        except Exception as e:
            logger.warning("Setting your location failed — %s", e)

    def _set_radius(self, radius: int):
        """Open the radius dropdown and select the given miles value.

        Locates the Radius combobox using get_by_role (which correctly resolves the
        aria-labelledby attribute), scrolls it into view, then simulates a real mouse
        click at the center of its bounding box using raw mouse events (move → down → up).
        This approach reliably triggers React's event handlers. Once the listbox appears,
        selects the option matching the requested miles value.
        """
        timeout = ACTION_TIMEOUT_MS
        option_text = f"{radius} miles"

        combobox = self.page.get_by_role("combobox", name="Radius")
        combobox.wait_for(state="visible", timeout=timeout)
        combobox.scroll_into_view_if_needed(timeout=timeout)
        random_delay(0.3, 0.5)

        box = combobox.bounding_box(timeout=timeout)
        if not box:
            logger.warning("Could not find the radius control on the page")
            return

        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2
        self.page.mouse.move(cx, cy)
        random_delay(0.1, 0.2)
        self.page.mouse.down()
        random_delay(0.05, 0.1)
        self.page.mouse.up()
        random_delay(0.5, 1)

        listbox = self.page.locator("[role='listbox']").first
        listbox.wait_for(state="visible", timeout=timeout)
        self.page.get_by_role("option", name=option_text).click(timeout=timeout)

    def _find_price_element(self, element, target_price: Optional[float] = None):
        """
        Find the price element in a listing using CSS selectors.
        
        Returns the Playwright locator for the price element if found, or None.
        If target_price is provided, only returns an element whose parsed price matches.
        """
        for selector in PRICE_SELECTORS:
            try:
                price_elem = element.locator(selector).first
                if price_elem.is_visible(timeout=1000):
                    price_text = price_elem.inner_text().strip()
                    parsed = parse_price(price_text)
                    if parsed and (target_price is None or parsed == target_price):
                        return price_elem
            except Exception as e:
                logger.debug("Could not find price element — %s", e)
                continue
        return None
    
    def _extract_price(self, element) -> Optional[float]:
        """
        Extract price from a listing element.
        
        Tries CSS selectors to find price elements (span/div with 'price' in class, or span with '$'),
        extracts the text, and parses it to float. Returns first valid price found or None.
        """
        price_elem = self._find_price_element(element)
        if price_elem:
            try:
                price_text = price_elem.inner_text().strip()
                return parse_price(price_text)
            except Exception as e:
                logger.debug("Could not read the price from this listing — %s", e)
        return None
    
    def _try_extract_title_by_dom_structure(self, element, price: float) -> str:
        """
        Try to extract title by locating price element and taking text before it.
        
        Uses DOM structure: finds the price element using the same selectors as _extract_price,
        locates its position in the element's text, and returns the first non-empty line that
        appears before the price. This leverages the fact that titles typically appear before
        prices in Facebook Marketplace DOM structure.
        """
        try:
            price_elem = self._find_price_element(element, target_price=price)
            if price_elem:
                all_text = element.inner_text().strip()
                price_text = price_elem.inner_text().strip()
                price_index = all_text.find(price_text)
                if price_index > 0:
                    title_candidate = all_text[:price_index].strip()
                    lines = title_candidate.split("\n")
                    for line in lines:
                        line = line.strip()
                        if line:
                            return line
        except Exception as e:
            logger.debug("Could not get listing title from page layout — %s", e)
        
        return ""
    
    def _try_extract_title_by_text_analysis(self, element) -> str:
        """
        Try to extract title by analyzing text lines, preferring those with letters.
        
        Splits element text into lines and analyzes them. First pass: returns first line
        containing letters (keeps lines with both letters and numbers like "iPhone 13").
        Skips lines that are only numbers/$ symbols. Second pass: if no lines with letters
        found, returns first line that isn't a pure price format.
        """
        try:
            all_lines = element.inner_text().strip().split("\n")
            
            for line in all_lines:
                line = line.strip()
                if not line:
                    continue
                if re.match(r'^[\$0-9.\s]+$', line):
                    continue
                if re.search(r'[A-Za-z]', line):
                    return line
            
            for line in all_lines:
                line = line.strip()
                if not line:
                    continue
                if re.match(r'^[\$0-9.\s]+$', line):
                    continue
                return line
        except Exception as e:
            logger.debug("Could not read listing title from text — %s", e)
        
        return ""
    
    def _extract_title(self, element, price: Optional[float]) -> str:
        """
        Extract title from a listing element using text analysis.
        
        Uses text analysis as the primary method since Facebook Marketplace listings follow
        a predictable text structure: prices first, then title, then location. Text analysis
        skips price-only lines and returns the first line containing letters. Falls back to
        DOM structure analysis if text analysis fails.
        """
        title = self._try_extract_title_by_text_analysis(element)
        if title:
            return title
        
        if price:
            title = self._try_extract_title_by_dom_structure(element, price)
            if title:
                return title
        
        return ""
    
    def _extract_location(self, element) -> str:
        """
        Extract location from a listing element by finding the span whose text is a location.

        Uses JavaScript DOM traversal to inspect each leaf-level span (no child spans)
        inside the listing card. The location span is identified by its content: text
        ending with a comma and a two-letter US state code (e.g. "San Jose, CA").
        If no location is found but shipping-related text is detected, returns "Shipped".
        Because each data field (price, title, location) lives in its own span element,
        checking individual spans avoids the old problem of title text bleeding into the
        location value.
        """
        try:
            result = element.evaluate("""
                (el) => {
                    const spans = el.querySelectorAll('span');
                    let location = '';
                    let hasShipping = false;
                    
                    for (const span of spans) {
                        if (span.children.length > 0) continue;
                        if (span.offsetParent === null) continue;
                        const text = span.textContent.trim();
                        
                        if (text && /,\\s*[A-Z]{2}$/.test(text)) {
                            location = text;
                            break;
                        }
                        
                        const lowerText = text.toLowerCase();
                        if (lowerText.includes('shipping') || 
                            lowerText.includes('ships to') ||
                            lowerText.includes('ships') ||
                            lowerText === 'shipped') {
                            hasShipping = true;
                        }
                    }
                    
                    if (location) {
                        return location;
                    }
                    if (hasShipping) {
                        return 'Shipped';
                    }
                    return '';
                }
            """)
            return result.strip() if result else ""
        except Exception as e:
            logger.debug("Could not read location for this listing — %s", e)
        return ""
    
    def _is_valid_description(self, text: str) -> bool:
        """
        Validate that extracted text is a real description and not Facebook internal code.
        
        Filters out JSON/script content, Facebook internal identifiers, and other non-description
        content. Returns True if the text appears to be a valid listing description.
        """
        if not text or len(text.strip()) < DESCRIPTION_MIN_LENGTH:
            return False
        
        text_lower = text.lower()
        
        # Filter out JSON-like content
        if text.strip().startswith("{") or text.strip().startswith("["):
            return False
        
        # Filter out Facebook internal identifiers
        facebook_internal_patterns = [
            "require",
            "cometssrmergedcontentinjector",
            "onpayloadreceived",
            "fizzrootid",
            "render_pass",
            "payloadtype",
            "readypreloaders",
            "clientrendererrors",
            "productrecoverableerrors",
            "adp_",
            "ssrb_root_content",
        ]
        
        for pattern in facebook_internal_patterns:
            if pattern in text_lower:
                return False
        
        # Filter out content that's mostly JSON structure
        if text.count("{") > 2 or text.count("}") > 2 or text.count("[") > 2:
            return False
        
        # Valid descriptions should have some normal text (letters, spaces, punctuation)
        # Not just special characters or JSON structure
        if not re.search(r'[A-Za-z]{3,}', text):
            return False
        
        return True
    
    def _extract_description_from_detail_page(self, url: str) -> str:
        """
        Navigate to listing detail page and extract description text under 'Details' section.
        
        Opens the listing URL in a new page, waits for it to load, finds the 'Details' text,
        and extracts the description content that appears underneath it. Tries multiple strategies:
        finding sibling elements, parent containers, and text analysis. Filters out Facebook
        internal JSON/script content. Returns empty string if description cannot be found or
        if navigation fails.
        """
        description = ""
        detail_page = None
        
        try:
            # Open detail page in new page to avoid losing search results context
            detail_page = self.context.new_page()
            detail_page.goto(url, wait_until="networkidle", timeout=15000)
            random_delay(2, 3)
            
            # Find "Details" text and get the description underneath
            details_selectors = [
                "span:has-text('Details')",
                "div:has-text('Details')",
                "h2:has-text('Details')",
                "h3:has-text('Details')",
            ]
            
            for selector in details_selectors:
                try:
                    details_element = detail_page.locator(selector).first
                    if details_element.is_visible(timeout=3000):
                        # Strategy 1: Try to find next sibling element containing description
                        try:
                            next_sibling = details_element.locator("xpath=following-sibling::*[1]")
                            if next_sibling.count() > 0:
                                sibling_text = next_sibling.inner_text().strip()
                                if self._is_valid_description(sibling_text):
                                    description = sibling_text
                                    break
                        except Exception:
                            pass
                        
                        # Strategy 2: Try to find description in following siblings (not just immediate)
                        try:
                            for i in range(1, DESCRIPTION_SIBLING_CHECK_COUNT + 1):
                                sibling = details_element.locator(f"xpath=following-sibling::*[{i}]")
                                if sibling.count() > 0:
                                    sibling_text = sibling.inner_text().strip()
                                    if self._is_valid_description(sibling_text):
                                        description = sibling_text
                                        break
                            if description:
                                break
                        except Exception:
                            pass
                        
                        # Strategy 3: Get parent container and extract text after "Details"
                        try:
                            parent = details_element.locator("xpath=..")
                            full_text = parent.inner_text().strip()
                            
                            # Extract text after "Details"
                            details_index = full_text.find("Details")
                            if details_index >= 0:
                                description_candidate = full_text[details_index + len("Details"):].strip()
                                # Remove any leading colons, dashes, or whitespace
                                description_candidate = description_candidate.lstrip(":-\n\r\t ")
                                # Take first reasonable chunk (stop at common separators or new sections)
                                lines = description_candidate.split("\n")
                                description_parts = []
                                for line in lines:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    # Stop if we hit "Location is approximate" marker
                                    if "location is approximate" in line.lower():
                                        break
                                    # Stop if we hit another section header (all caps or common patterns)
                                    if re.match(r'^[A-Z\s]{10,}$', line) and len(line) > 15:
                                        break
                                    description_parts.append(line)
                                    if len(description_parts) >= DESCRIPTION_MAX_LINES:
                                        break
                                
                                description_candidate = "\n".join(description_parts).strip()
                                if self._is_valid_description(description_candidate):
                                    description = description_candidate
                                    break
                        except Exception:
                            pass
                        
                        # Strategy 4: Look for description in nearby div/span elements
                        try:
                            nearby_elements = detail_page.locator("xpath=//span[contains(text(), 'Details')]/following::div[1] | //div[contains(text(), 'Details')]/following::div[1] | //h2[contains(text(), 'Details')]/following::div[1]")
                            if nearby_elements.count() > 0:
                                nearby_text = nearby_elements.first.inner_text().strip()
                                if self._is_valid_description(nearby_text):
                                    description = nearby_text
                                    break
                        except Exception:
                            pass
                except Exception:
                    continue
            
        except Exception as e:
            logger.debug(f"Failed to extract description from {url}: {e}")
        finally:
            if detail_page:
                try:
                    detail_page.close()
                except Exception:
                    pass
        
        return description
    
    def _scroll_page_to_load_content(self):
        """Scroll the page to load more listing content."""
        for _ in range(SCROLL_ATTEMPTS):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(1, 2)
    
    def _find_listing_elements(self) -> List:
        """
        Find listing elements on the page using multiple CSS selectors.
        
        Tries selectors in order: article elements, marketplace listing test IDs,
        and marketplace item links. Returns list of Playwright locators.
        """
        listing_container_selectors = [
            "div[role='article']",
            "div[data-testid='marketplace-listing']",
            "a[href*='/marketplace/item/']",
        ]
        
        for selector in listing_container_selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    logger.debug("Found %d listing cards on the page", len(elements))
                    return elements
            except Exception:
                continue
        
        logger.warning("We could not find any listing cards on the page. Facebook may have changed their layout.")
        return []
    
    def _extract_listing_from_element(self, element, extract_descriptions: bool = False) -> Optional[Listing]:
        """
        Extract a single listing from a listing element.
        
        Extracts URL, price, title, and location from the element. Optionally navigates
        to the listing's detail page to extract the full description if extract_descriptions
        is True. Validates that price is valid and title is not a price format. Returns
        Listing object if valid, or None if extraction fails or data is invalid.
        """
        try:
            url = element.get_attribute("href") or ""
            if not url.startswith("http"):
                url = f"https://www.facebook.com{url}" if url.startswith("/") else ""
            
            if not url:
                return None
            
            price = self._extract_price(element)
            
            if not is_valid_listing_price(price):
                return None
            
            title = self._extract_title(element, price)
            
            # Final validation: only skip if title is EXACTLY a price format (no letters)
            if title and re.match(r'^[\$0-9.\s]+$', title):
                title = ""
            
            location = self._extract_location(element)
            
            # Extract description from detail page if enabled
            if extract_descriptions:
                description = self._extract_description_from_detail_page(url)
            else:
                description = ""  # Skip description extraction for performance
            
            if title and price:
                return Listing(
                    title=title,
                    price=price,
                    location=location or LOCATION_UNKNOWN,
                    url=url,
                    description=description
                )
            
            return None
            
        except Exception as e:
            logger.debug("Could not read one of the listings (missing price or title) — %s", e)
            return None
    
    def _extract_listings(
        self,
        max_listings: int = 20,
        on_listing_found=None,
        extract_descriptions: bool = False,
    ) -> List[Listing]:
        """
        Extract up to max_listings from the current Marketplace results page.

        Scrolls to load content, locates listing DOM elements, then iterates
        up to max_listings of them and parses each into a Listing.
        """
        listings = []
        try:
            self._scroll_page_to_load_content()
            listing_elements = self._find_listing_elements()
            total = min(len(listing_elements), max_listings)
            for element in listing_elements[:max_listings]:
                listing = self._extract_listing_from_element(element, extract_descriptions=extract_descriptions)
                if listing:
                    idx = len(listings) + 1
                    label = f"[{idx}/{total}] Retrieved:" if total else "Retrieved:"
                    log_listing_box_sep(logger)
                    log_data_block(
                        logger, label,
                        title=listing.title, price=listing.price, location=listing.location, url=listing.url,
                    )
                    if listing.description:
                        logger.debug(f"  Description: {listing.description}")
                    log_listing_box_sep(logger)
                    listings.append(listing)
                    if on_listing_found:
                        on_listing_found(listing, len(listings))
            
        except Exception as e:
            logger.warning("Reading the list of listings from the page failed — %s", e)
        
        return listings
    
    def search_marketplace(
        self,
        query: str,
        zip_code: str,
        radius: int = 25,
        max_listings: int = 20,
        on_listing_found=None,
        extract_descriptions: bool = False,
        step_sep: Optional[str] = "main",
        on_inspector_url: Optional[Callable[[str], None]] = None,
    ) -> List[Listing]:
        """
        Run a Marketplace search and return up to max_listings results.

        step_sep: "main" = main step separator line; "sub" = section separator (within Step 2); None = plain title line only.
        on_inspector_url: optional callback invoked with the DevTools inspector URL when browser is created (headed mode).
        """
        self._on_inspector_url = on_inspector_url
        if step_sep == "main":
            logger.info("FB Marketplace search")
            log_data_block(
                logger, "",
                query=query, zip=zip_code, radius=f"{radius}mi", max=max_listings,
                descriptions="on" if extract_descriptions else "off"
            )
        elif step_sep == "sub":
            logger.info("FB Marketplace search")
            set_step_indent("  ")
            log_data_block(
                logger, "",
                indent="  ",
                query=query, zip=zip_code, radius=f"{radius}mi", max=max_listings,
                descriptions="on" if extract_descriptions else "off"
            )
        else:
            log_data_block(
                logger, "FB Marketplace search",
                query=query, zip=zip_code, radius=f"{radius}mi", max=max_listings,
                descriptions="on" if extract_descriptions else "off"
            )
        if not extract_descriptions:
            logger.info("ℹ️ Descriptions toggled off — not fetching listing descriptions")
        try:
            with wait_status(logger, "Facebook Marketplace search"):
                if not self.browser:
                    self._create_browser()
                self._goto_search_results(query)
                self._set_location(zip_code, radius)
                listings = self._extract_listings(
                    max_listings=max_listings,
                    on_listing_found=on_listing_found,
                    extract_descriptions=extract_descriptions,
                )
            return listings
        finally:
            clear_step_indent()
    
    def close(self):
        """Close the browser and cleanup resources.

        Each step is wrapped independently so a failure in one (e.g. page
        already closed) does not prevent the remaining resources from being
        released. The Chrome subprocess is terminated and, if it doesn't
        exit within 5 seconds, killed.
        """
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
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


def search_marketplace(
    query: str,
    zip_code: str,
    radius: int = 25,
    max_listings: int = 20,
    headless: bool = None,
    on_listing_found=None,
    extract_descriptions: bool = False,
    step_sep: Optional[str] = "main",
    on_inspector_url: Optional[Callable[[str], None]] = None,
) -> List[Listing]:
    """
    Run a one-off Facebook Marketplace search and return the results.

    step_sep: "main" = main step separator; "sub" = section separator; None = plain title only.
    on_inspector_url: optional callback invoked with the DevTools inspector URL when browser is created (headed mode).
    """
    scraper = FBMarketplaceScraper(headless=headless)
    try:
        return scraper.search_marketplace(
            query, zip_code, radius,
            max_listings=max_listings,
            on_listing_found=on_listing_found,
            extract_descriptions=extract_descriptions,
            step_sep=step_sep,
            on_inspector_url=on_inspector_url,
        )
    finally:
        scraper.close()

