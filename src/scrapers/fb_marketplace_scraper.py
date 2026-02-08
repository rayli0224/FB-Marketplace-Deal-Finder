"""
Facebook Marketplace Scraper

Scrapes Facebook Marketplace listings using Playwright for better anti-detection.
Supports searching by query, zip code, and radius.

AUTHENTICATION:
Facebook Marketplace requires login. To use this scraper:
1. Export your Facebook cookies using a browser extension (e.g., "EditThisCookie" or "Cookie-Editor")
2. Save them as JSON to: cookies/facebook_cookies.json
3. The scraper will automatically load them

Cookie JSON format (array of objects):
[
  {"name": "c_user", "value": "...", "domain": ".facebook.com", "path": "/", ...},
  {"name": "xs", "value": "...", "domain": ".facebook.com", "path": "/", ...},
  ...
]
"""

import re
import os
import json
import logging
from dataclasses import dataclass
from typing import Optional, List
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError
from src.scrapers.utils import random_delay, parse_price, is_valid_listing_price
from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix (auto-detects DEBUG from env/--debug flag)
logger = setup_colored_logger("fb_scraper")

# Default cookie file path
COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "/app/cookies/facebook_cookies.json")


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
    
    MARKETPLACE_URL = "https://www.facebook.com/marketplace"
    
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
    
    def _create_browser(self):
        """Create a Playwright browser with stealth settings and load cookies."""
        self.playwright = sync_playwright().start()
        
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1920,1080",
            ]
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
    
    def _set_location(self, zip_code: str, radius: int):
        """Navigate to Facebook Marketplace and set location via zip code."""
        try:
            self.page.goto(self.MARKETPLACE_URL, wait_until="networkidle", timeout=30000)
            random_delay(2, 4)
            
            try:
                self.page.wait_for_selector("h1", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            
            location_selectors = [
                "div[aria-label*='location']",
                "div[aria-label*='Location']",
                "span:has-text('Location')",
            ]
            
            location_clicked = False
            for selector in location_selectors:
                try:
                    if selector.startswith("//"):
                        location_button = self.page.locator(selector).first
                    else:
                        location_button = self.page.locator(selector).first
                    
                    if location_button.is_visible(timeout=5000):
                        location_button.click()
                        random_delay(1, 2)
                        location_clicked = True
                        break
                except (PlaywrightTimeoutError, Exception):
                    continue
            
            if not location_clicked:
                try:
                    location_input = self.page.locator("input[placeholder*='zip'], input[placeholder*='Zip'], input[type='text']").first
                    if location_input.is_visible(timeout=5000):
                        location_input.fill(zip_code)
                        random_delay(1, 2)
                        location_input.press("Enter")
                        random_delay(1, 2)
                except PlaywrightTimeoutError:
                    pass
            
            if location_clicked:
                try:
                    zip_input = self.page.locator("input[placeholder*='zip'], input[placeholder*='Zip'], input[type='text']").first
                    if zip_input.is_visible(timeout=5000):
                        zip_input.fill(zip_code)
                        random_delay(1, 2)
                        
                        apply_selectors = [
                            "div[aria-label='Apply']",
                            "button:has-text('Apply')",
                            "button:has-text('Done')",
                        ]
                        
                        for selector in apply_selectors:
                            try:
                                apply_button = self.page.locator(selector).first
                                if apply_button.is_visible(timeout=3000):
                                    apply_button.click()
                                    random_delay(1, 2)
                                    break
                            except PlaywrightTimeoutError:
                                continue
                except PlaywrightTimeoutError:
                    pass
            
        except Exception:
            pass
    
    def _search(self, query: str):
        """Enter search query and wait for results."""
        try:
            search_selectors = [
                "input[aria-label='Search Marketplace']",
                "input[placeholder*='Search']",
                "input[type='search']",
            ]
            
            search_bar = None
            for selector in search_selectors:
                try:
                    search_bar = self.page.locator(selector).first
                    if search_bar.is_visible(timeout=5000):
                        break
                except PlaywrightTimeoutError:
                    continue
            
            if not search_bar:
                raise Exception("Could not find search bar")
            
            search_bar.fill(query)
            random_delay(0.5, 1.0)
            search_bar.press("Enter")
            
            random_delay(3, 5)
            
            try:
                listing_selectors = [
                    "div[role='main']",
                    "div[data-testid='marketplace-search-results']",
                    "div[class*='listing']",
                ]
                
                for selector in listing_selectors:
                    try:
                        self.page.wait_for_selector(selector, timeout=10000)
                        break
                    except PlaywrightTimeoutError:
                        continue
            except Exception:
                pass
            
        except Exception:
            raise
    
    def _extract_price(self, element) -> Optional[float]:
        """
        Extract price from a listing element.
        
        Tries CSS selectors to find price elements (span/div with 'price' in class, or span with '$'),
        extracts the text, and parses it to float. Returns first valid price found or None.
        """
        price_selectors = [
            "span[class*='price']",
            "div[class*='price']",
            "span:has-text('$')",
        ]
        
        for selector in price_selectors:
            try:
                price_elem = element.locator(selector).first
                if price_elem.is_visible(timeout=1000):
                    price_text = price_elem.inner_text().strip()
                    price = parse_price(price_text)
                    if price:
                        return price
            except:
                continue
        
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
            price_selectors = [
                "span[class*='price']",
                "div[class*='price']",
                "span:has-text('$')",
            ]
            
            price_elem = None
            for selector in price_selectors:
                try:
                    candidate = element.locator(selector).first
                    if candidate.is_visible(timeout=1000):
                        price_text = candidate.inner_text().strip()
                        parsed = parse_price(price_text)
                        if parsed == price:
                            price_elem = candidate
                            break
                except:
                    continue
            
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
        except:
            pass
        
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
        except:
            pass
        
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
        Extract location from a listing element.
        
        Tries CSS selectors for location elements. If that fails, uses regex to find
        location pattern "City Name, ST" (e.g., "New York, NY") in the element's text.
        """
        location_selectors = [
            "span[class*='location']",
            "div[class*='location']",
        ]
        
        for selector in location_selectors:
            try:
                location_elem = element.locator(selector).first
                if location_elem.is_visible(timeout=1000):
                    location = location_elem.inner_text().strip()
                    if location:
                        return location
            except:
                continue
        
        try:
            full_text = element.inner_text()
            location_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})', full_text)
            if location_match:
                return location_match.group(1)
        except:
            pass
        
        return ""
    
    def _extract_description_from_detail_page(self, url: str) -> str:
        """
        Navigate to listing detail page and extract description text under 'Details' section.
        
        Opens the listing URL in a new page, waits for it to load, finds the 'Details' text,
        and extracts the description content that appears underneath it. Tries multiple strategies:
        finding sibling elements, parent containers, and text analysis. Returns empty string
        if description cannot be found or if navigation fails.
        """
        description = ""
        
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
                                if sibling_text and len(sibling_text) > 10:  # Reasonable description length
                                    description = sibling_text
                                    break
                        except:
                            pass
                        
                        # Strategy 2: Get parent container and extract text after "Details"
                        try:
                            parent = details_element.locator("xpath=..")
                            full_text = parent.inner_text().strip()
                            
                            # Extract text after "Details"
                            details_index = full_text.find("Details")
                            if details_index >= 0:
                                description_candidate = full_text[details_index + len("Details"):].strip()
                                # Remove any leading colons, dashes, or whitespace
                                description_candidate = description_candidate.lstrip(":-\n\r\t ")
                                if description_candidate and len(description_candidate) > 10:
                                    description = description_candidate
                                    break
                        except:
                            pass
                except:
                    continue
            
            detail_page.close()
            
        except Exception:
            # If anything fails, ensure we close the page and return empty string
            try:
                detail_page.close()
            except:
                pass
        
        return description
    
    def _scroll_page_to_load_content(self):
        """Scroll the page to load more listing content."""
        scroll_attempts = 3
        for _ in range(scroll_attempts):
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(1, 2)
    
    def _find_listing_elements(self) -> List:
        """
        Find listing elements on the page using multiple CSS selectors.
        
        Tries selectors in order: article elements, marketplace listing test IDs,
        and marketplace item links. Falls back to marketplace item links if no
        elements found. Returns list of Playwright locators.
        """
        listing_container_selectors = [
            "div[role='article']",
            "div[data-testid='marketplace-listing']",
            "a[href*='/marketplace/item/']",
        ]
        
        listing_elements = []
        for selector in listing_container_selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    listing_elements = elements
                    break
            except Exception:
                continue
        
        if not listing_elements:
            listing_elements = self.page.locator("a[href*='/marketplace/item/']").all()
        
        return listing_elements
    
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
                    location=location or "Unknown",
                    url=url,
                    description=description
                )
            
            return None
            
        except Exception:
            return None
    
    def _extract_listings(self, on_listing_found=None, extract_descriptions: bool = False) -> List[Listing]:
        """
        Extract listings from the current Facebook Marketplace page.
        
        Scrolls the page to load more content, finds listing elements, and extracts
        data from each element using helper functions. Optionally calls a callback
        each time a listing is found. Returns list of successfully extracted listings.
        """
        listings = []
        
        try:
            self._scroll_page_to_load_content()
            listing_elements = self._find_listing_elements()
            
            for element in listing_elements[:50]:
                listing = self._extract_listing_from_element(element, extract_descriptions=extract_descriptions)
                if listing:
                    logger.debug(
                        f"Extracted FB listing:\n"
                        f"  Title: {listing.title}\n"
                        f"  Price: ${listing.price:.2f}\n"
                        f"  Location: {listing.location}\n"
                        f"  URL: {listing.url}\n"
                        f"  Description: {listing.description}"
                    )
                    listings.append(listing)
                    if on_listing_found:
                        on_listing_found(listing, len(listings))
            
        except Exception:
            pass
        
        return listings
    
    def search_marketplace(self, query: str, zip_code: str, radius: int = 25, on_listing_found=None, extract_descriptions: bool = False) -> List[Listing]:
        """Search Facebook Marketplace for listings matching the query."""
        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info(f"║  🔍 Starting FB Marketplace Search")
        logger.info(f"║  Query: '{query}' | Zip: {zip_code} | Radius: {radius}mi")
        if extract_descriptions:
            logger.info(f"║  ⚠️  Description extraction enabled (slower)")
        logger.info("╚" + "═" * 78 + "╝")
        logger.info("")
        
        try:
            if not self.browser:
                self._create_browser()
            
            self._set_location(zip_code, radius)
            self._search(query)
            listings = self._extract_listings(on_listing_found=on_listing_found, extract_descriptions=extract_descriptions)
            
            logger.info("")
            logger.info(f"✅ Search completed. Found {len(listings)} listings")
            logger.info("")
            return listings
            
        except Exception:
            raise
    
    def close(self):
        """Close the browser and cleanup resources."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


def search_marketplace(
    query: str,
    zip_code: str,
    radius: int = 25,
    headless: bool = None,
    on_listing_found=None,
    extract_descriptions: bool = False,
) -> List[Listing]:
    """Convenience function to search Facebook Marketplace."""
    scraper = FBMarketplaceScraper(headless=headless)
    try:
        return scraper.search_marketplace(query, zip_code, radius, on_listing_found=on_listing_found, extract_descriptions=extract_descriptions)
    finally:
        scraper.close()

