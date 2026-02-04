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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default cookie file path
COOKIES_FILE = os.environ.get("FB_COOKIES_FILE", "/app/cookies/facebook_cookies.json")


@dataclass
class Listing:
    title: str
    price: float
    location: str
    url: str
    
    def __str__(self) -> str:
        return f"Listing(title='{self.title}', price=${self.price:.2f}, location='{self.location}', url='{self.url}')"


class FBMarketplaceScraper:
    
    MARKETPLACE_URL = "https://www.facebook.com/marketplace"
    
    def __init__(self, headless: bool = None, cookies_file: str = None):
        """
        Initialize the Facebook Marketplace scraper.
        
        Args:
            headless: Run browser in headless mode
            cookies_file: Path to JSON file containing Facebook cookies
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
            logger.warning(f"Cookies file not found: {self.cookies_file}")
            logger.info("To authenticate, export your Facebook cookies to this file.")
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
            
            logger.info(f"Loaded {len(playwright_cookies)} cookies from {self.cookies_file}")
            return playwright_cookies
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in cookies file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading cookies: {e}")
            return []
    
    def _create_browser(self):
        """Create a Playwright browser with stealth settings and load cookies."""
        logger.info("Initializing Playwright browser")
        
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
            logger.info("Cookies loaded into browser context")
        else:
            logger.warning("No cookies loaded - Facebook will likely require login!")
        
        self.page = self.context.new_page()
        
        logger.info("Browser initialized successfully")
    
    def _set_location(self, zip_code: str, radius: int):
        """Navigate to Facebook Marketplace and set location via zip code."""
        logger.info(f"Setting location to zip code {zip_code} with radius {radius} miles")
        
        try:
            self.page.goto(self.MARKETPLACE_URL, wait_until="networkidle", timeout=30000)
            random_delay(2, 4)
            
            try:
                self.page.wait_for_selector("h1", timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning("Page load timeout, continuing anyway")
            
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
                except (PlaywrightTimeoutError, Exception) as e:
                    logger.debug(f"Location selector {selector} failed: {e}")
                    continue
            
            if not location_clicked:
                logger.warning("Could not find location button, trying alternative method")
                try:
                    location_input = self.page.locator("input[placeholder*='zip'], input[placeholder*='Zip'], input[type='text']").first
                    if location_input.is_visible(timeout=5000):
                        location_input.fill(zip_code)
                        random_delay(1, 2)
                        location_input.press("Enter")
                        random_delay(1, 2)
                except PlaywrightTimeoutError:
                    logger.warning("Could not set location via input field")
            
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
                    logger.warning("Could not enter zip code in location picker")
            
            logger.info("Location setting completed")
            
        except Exception as e:
            logger.error(f"Error setting location: {e}")
    
    def _search(self, query: str):
        """Enter search query and wait for results."""
        logger.info(f"Searching for: '{query}'")
        
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
            except Exception as e:
                logger.warning(f"Could not confirm results loaded: {e}")
            
            logger.info("Search completed")
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            raise
    
    def _extract_listings(self) -> List[Listing]:
        """Extract listings from the current page."""
        logger.info("Extracting listings from page")
        
        listings = []
        
        try:
            scroll_attempts = 3
            for _ in range(scroll_attempts):
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                random_delay(1, 2)
            
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
                        logger.info(f"Found {len(elements)} listings using selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            if not listing_elements:
                logger.warning("No listing elements found with standard selectors, trying alternative approach")
                listing_elements = self.page.locator("a[href*='/marketplace/item/']").all()
            
            for element in listing_elements[:50]:
                try:
                    url = element.get_attribute("href") or ""
                    if not url.startswith("http"):
                        url = f"https://www.facebook.com{url}" if url.startswith("/") else ""
                    
                    if not url:
                        continue
                    
                    title = ""
                    title_selectors = [
                        "span[class*='title']",
                        "div[class*='title']",
                        "span:has-text('')",
                    ]
                    
                    for selector in title_selectors:
                        try:
                            title_elem = element.locator(selector).first
                            if title_elem.is_visible(timeout=1000):
                                title = title_elem.inner_text().strip()
                                if title:
                                    break
                        except:
                            continue
                    
                    if not title:
                        try:
                            title = element.inner_text().strip().split("\n")[0]
                        except:
                            pass
                    
                    price = None
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
                                    break
                        except:
                            continue
                    
                    if not is_valid_listing_price(price):
                        continue
                    
                    location = ""
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
                                    break
                        except:
                            continue
                    
                    if not location:
                        try:
                            full_text = element.inner_text()
                            location_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s*[A-Z]{2})', full_text)
                            if location_match:
                                location = location_match.group(1)
                        except:
                            pass
                    
                    if title and price:
                        listing = Listing(
                            title=title,
                            price=price,
                            location=location or "Unknown",
                            url=url
                        )
                        listings.append(listing)
                        
                except Exception as e:
                    logger.debug(f"Error extracting listing: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(listings)} listings")
            
        except Exception as e:
            logger.error(f"Error extracting listings: {e}")
        
        return listings
    
    def search_marketplace(self, query: str, zip_code: str, radius: int = 25) -> List[Listing]:
        """Search Facebook Marketplace for listings matching the query."""
        logger.info(f"Starting marketplace search: query='{query}', zip={zip_code}, radius={radius}mi")
        
        try:
            if not self.browser:
                self._create_browser()
            
            self._set_location(zip_code, radius)
            self._search(query)
            listings = self._extract_listings()
            
            logger.info(f"Search completed. Found {len(listings)} listings")
            return listings
            
        except Exception as e:
            logger.error(f"Error during marketplace search: {e}")
            raise
    
    def close(self):
        """Close the browser and cleanup resources."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser closed and resources cleaned up")


def search_marketplace(
    query: str,
    zip_code: str,
    radius: int = 25,
    headless: bool = None,
) -> List[Listing]:
    """Convenience function to search Facebook Marketplace."""
    scraper = FBMarketplaceScraper(headless=headless)
    try:
        return scraper.search_marketplace(query, zip_code, radius)
    finally:
        scraper.close()

