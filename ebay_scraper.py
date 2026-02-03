"""
eBay Sold Items Price Analyzer

Fetches recently sold items from eBay and calculates price statistics
to help determine fair market value and identify good deals.

Author: Auto-generated
"""

import re
import time
import random
import statistics
from dataclasses import dataclass
from typing import Optional
import logging

# Third-party imports
import requests
import numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Try to import selenium-stealth for anti-detection
try:
    from selenium_stealth import stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
    print("Warning: selenium-stealth not installed. Run: pip install selenium-stealth")

# Try to import undetected-chromedriver (best anti-detection)
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    UC_AVAILABLE = False
    print("Warning: undetected-chromedriver not installed. Run: pip install undetected-chromedriver")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PriceStats:
    """Container for price statistics results."""
    search_term: str
    sample_size: int
    average: float
    median: float
    min_price: float
    max_price: float
    std_dev: float
    percentile_25: float
    percentile_75: float
    raw_prices: list[float]
    
    def get_deal_assessment(self, price: float) -> str:
        """
        Assess if a given price is a good deal.
        
        Args:
            price: The price to assess
            
        Returns:
            String describing the deal quality
        """
        if price <= self.percentile_25:
            return "🔥 GREAT DEAL - Below 25th percentile"
        elif price <= self.median:
            return "✅ GOOD DEAL - Below median"
        elif price <= self.percentile_75:
            return "⚠️ FAIR PRICE - Above median but reasonable"
        else:
            return "❌ OVERPRICED - Above 75th percentile"
    
    def __str__(self) -> str:
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 eBay Sold Items Price Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Search Term: {self.search_term}
Sample Size: {self.sample_size} sold items

💰 Price Statistics:
   Average:     ${self.average:.2f}
   Median:      ${self.median:.2f}
   Min:         ${self.min_price:.2f}
   Max:         ${self.max_price:.2f}
   Std Dev:     ${self.std_dev:.2f}

📈 Deal Thresholds:
   Great Deal (≤25%):  ${self.percentile_25:.2f}
   Fair Price (≤50%):  ${self.median:.2f}
   Max Fair (≤75%):    ${self.percentile_75:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class EbayScraper:
    """
    Scrapes eBay sold listings to analyze pricing data.
    
    Uses Selenium with stealth techniques to avoid detection.
    """
    
    # Common user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    def __init__(self, headless: bool = None):
        """
        Initialize the eBay scraper.
        
        Args:
            headless: Run browser in headless mode (invisible).
                      If None, auto-detects: uses non-headless if DISPLAY is set (Xvfb).
        """
        import os
        if headless is None:
            # Auto-detect: if DISPLAY is set (Xvfb), use non-headless for better stealth
            self.headless = os.environ.get("DISPLAY") is None
        else:
            self.headless = headless
        self.driver = None
    
    def _create_driver(self):
        """Create a Chrome WebDriver with undetected-chromedriver."""
        
        # === USE UNDETECTED-CHROMEDRIVER (best anti-detection) ===
        if UC_AVAILABLE:
            logger.info("Using undetected-chromedriver")
            
            options = uc.ChromeOptions()
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-size=1920,1080")
            
            # Let undetected-chromedriver download and manage Chrome automatically
            driver = uc.Chrome(
                options=options,
                headless=self.headless,
            )
            return driver
        
        # === FALLBACK: Regular Selenium ===
        logger.warning("undetected-chromedriver not available, using regular Selenium (may get blocked)")
        
        import os
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless=new")
        
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"--user-agent={random.choice(self.USER_AGENTS)}")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        
        chrome_bin = os.environ.get("CHROME_BIN")
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        
        if chrome_bin:
            chrome_options.binary_location = chrome_bin
        
        if chromedriver_path:
            service = Service(chromedriver_path)
        else:
            service = Service(ChromeDriverManager().install())
        
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        if STEALTH_AVAILABLE:
            stealth(driver, languages=["en-US", "en"], vendor="Google Inc.",
                    platform="Win32", webgl_vendor="Intel Inc.",
                    renderer="Intel Iris OpenGL Engine", fix_hairline=True)
        
        return driver
    
    def _random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Add a random delay to mimic human behavior."""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """
        Parse a price string into a float.
        
        Handles formats like:
        - "$123.45"
        - "$100.00 to $200.00" (returns average)
        - "£123.45" (other currencies)
        
        Args:
            price_text: The price string to parse
            
        Returns:
            Parsed price as float, or None if parsing fails
        """
        try:
            # Find all price values in the string
            pattern = r'[\d,]+\.?\d*'
            matches = re.findall(pattern, price_text.replace(',', ''))
            
            if not matches:
                return None
            
            prices = [float(m) for m in matches if m and float(m) > 0]
            
            if not prices:
                return None
            
            # If range (e.g., "$10 to $20"), return average
            if len(prices) >= 2:
                return sum(prices) / len(prices)
            
            return prices[0]
            
        except (ValueError, IndexError):
            return None
    
    def _extract_prices_from_page(self, driver: webdriver.Chrome, max_items: int) -> list[float]:
        """
        Extract prices from the current eBay search results page.
        
        Args:
            driver: Selenium WebDriver instance
            max_items: Maximum number of items to extract
            
        Returns:
            List of extracted prices
        """
        prices = []
        
        try:
            # Wait for listings to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.s-item"))
            )
            
            # Find all listing items
            items = driver.find_elements(By.CSS_SELECTOR, "li.s-item")
            
            for item in items[:max_items + 5]:  # Get a few extra in case some fail
                if len(prices) >= max_items:
                    break
                    
                try:
                    # Try to find the price element
                    price_elem = item.find_element(By.CSS_SELECTOR, "span.s-item__price")
                    price_text = price_elem.text
                    
                    # Skip "Shop on eBay" placeholder items
                    title_elem = item.find_elements(By.CSS_SELECTOR, "div.s-item__title span")
                    if title_elem and "Shop on eBay" in title_elem[0].text:
                        continue
                    
                    price = self._parse_price(price_text)
                    if price and price > 0:
                        prices.append(price)
                        
                except NoSuchElementException:
                    continue
                    
        except TimeoutException:
            logger.warning("Timeout waiting for listings to load")
            
        return prices
    
    def get_sold_item_stats(
        self,
        search_term: str,
        n_items: int = 100,
        excluded_keywords: Optional[list[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> Optional[PriceStats]:
        """
        Search eBay for sold items and calculate price statistics.
        
        Args:
            search_term: The item to search for
            n_items: Target number of sold items to analyze (50-100 recommended)
            excluded_keywords: Words to exclude from search (e.g., ["broken", "parts"])
            min_price: Minimum price filter
            max_price: Maximum price filter
            
        Returns:
            PriceStats object with calculated statistics, or None if failed
        """
        logger.info(f"Searching eBay for sold items: '{search_term}'")
        
        try:
            self.driver = self._create_driver()
            
            # Build the search URL with sold items filter
            search_query = search_term
            if excluded_keywords:
                search_query += " -" + " -".join(excluded_keywords)
            
            # URL encode the search query
            encoded_query = requests.utils.quote(search_query)
            
            # Build URL with filters:
            # LH_Sold=1 - Sold items only
            # LH_Complete=1 - Completed listings
            # _sop=13 - Sort by end date (most recent first)
            # _ipg=240 - Items per page (max)
            url = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}&LH_Sold=1&LH_Complete=1&_sop=13&_ipg=240"
            
            # Add price filters if specified
            if min_price is not None:
                url += f"&_udlo={min_price}"
            if max_price is not None:
                url += f"&_udhi={max_price}"
            
            logger.info(f"Fetching URL: {url}")
            
            # First visit eBay homepage to establish session (helps avoid detection)
            self.driver.get("https://www.ebay.com")
            self._random_delay(2, 4)
            
            # Now navigate to search results
            self.driver.get(url)
            self._random_delay(3, 5)
            
            # Check for CAPTCHA or blocking
            page_source_lower = self.driver.page_source.lower()
            if any(term in page_source_lower for term in ["captcha", "robot", "verify you're human", "blocked"]):
                logger.error("CAPTCHA/block detected! Try again later or use non-headless mode.")
                logger.info("Tip: Wait a few minutes, or try a different search term.")
                return None
            
            # Extract prices from results
            all_prices = []
            pages_fetched = 0
            max_pages = (n_items // 60) + 2  # Calculate how many pages we might need
            
            while len(all_prices) < n_items and pages_fetched < max_pages:
                page_prices = self._extract_prices_from_page(self.driver, n_items - len(all_prices))
                
                if not page_prices:
                    logger.warning("No prices found on page")
                    break
                
                all_prices.extend(page_prices)
                pages_fetched += 1
                logger.info(f"Page {pages_fetched}: Found {len(page_prices)} prices (Total: {len(all_prices)})")
                
                # Check if we need more pages
                if len(all_prices) < n_items:
                    try:
                        # Try to click "Next" button
                        next_button = self.driver.find_element(
                            By.CSS_SELECTOR, 
                            "a.pagination__next"
                        )
                        if next_button:
                            next_button.click()
                            self._random_delay(2, 4)
                        else:
                            break
                    except NoSuchElementException:
                        logger.info("No more pages available")
                        break
            
            # Trim to requested number
            all_prices = all_prices[:n_items]
            
            if len(all_prices) < 3:
                logger.error(f"Not enough data: only found {len(all_prices)} prices")
                return None
            
            # Calculate statistics
            stats = PriceStats(
                search_term=search_term,
                sample_size=len(all_prices),
                average=statistics.mean(all_prices),
                median=statistics.median(all_prices),
                min_price=min(all_prices),
                max_price=max(all_prices),
                std_dev=statistics.stdev(all_prices) if len(all_prices) > 1 else 0,
                percentile_25=float(np.percentile(all_prices, 25)),
                percentile_75=float(np.percentile(all_prices, 75)),
                raw_prices=sorted(all_prices),
            )
            
            logger.info(f"Successfully analyzed {stats.sample_size} sold items")
            return stats
            
        except Exception as e:
            logger.error(f"Error scraping eBay: {e}")
            return None
            
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None


class EbayAPIClient:
    """
    Alternative client using eBay's official Browse API.
    
    Note: Requires API credentials from developer.ebay.com
    The Browse API doesn't directly support sold items, so this is 
    primarily for active listings comparison.
    """
    
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    
    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize the eBay API client.
        
        Args:
            client_id: eBay API client ID (App ID)
            client_secret: eBay API client secret (Cert ID)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = None
        self._token_expiry = 0
    
    def _get_access_token(self) -> str:
        """Get or refresh the OAuth access token."""
        import base64
        
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        # Create Basic auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
        
        response = requests.post(self.TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        self._access_token = token_data["access_token"]
        self._token_expiry = time.time() + token_data.get("expires_in", 7200) - 60
        
        return self._access_token
    
    def search_items(self, search_term: str, limit: int = 50) -> list[dict]:
        """
        Search for active listings (not sold items).
        
        Note: The Browse API doesn't support sold items directly.
        Use EbayScraper for sold items data.
        
        Args:
            search_term: The item to search for
            limit: Maximum number of results
            
        Returns:
            List of item dictionaries
        """
        token = self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        }
        
        params = {
            "q": search_term,
            "limit": min(limit, 200),
        }
        
        response = requests.get(
            self.BROWSE_API_URL,
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get("itemSummaries", [])


def get_sold_item_stats(
    search_term: str,
    n_items: int = 100,
    excluded_keywords: Optional[list[str]] = None,
    headless: bool = None,
) -> Optional[PriceStats]:
    """
    Convenience function to get sold item statistics.
    
    This is the main entry point for the module.
    
    Args:
        search_term: The item to search for (e.g., "iPhone 13 Pro 128GB")
        n_items: Number of sold items to analyze (50-100 recommended)
        excluded_keywords: Words to exclude (e.g., ["broken", "parts", "locked"])
        headless: Run browser invisibly (True) or visibly (False)
        
    Returns:
        PriceStats object with price analysis, or None if failed
        
    Example:
        >>> stats = get_sold_item_stats("Nintendo Switch OLED", n_items=50)
        >>> print(stats)
        >>> print(stats.get_deal_assessment(280.00))
    """
    scraper = EbayScraper(headless=headless)
    return scraper.get_sold_item_stats(
        search_term=search_term,
        n_items=n_items,
        excluded_keywords=excluded_keywords,
    )


# =============================================================================
# Interactive CLI
# =============================================================================

def interactive_mode():
    """Run the scraper in interactive command-line mode."""
    print("\n" + "=" * 55)
    print("  eBay Sold Items Price Analyzer - Interactive Mode")
    print("=" * 55)
    
    while True:
        print("\nOptions:")
        print("  1. Search for an item")
        print("  2. Exit")
        
        choice = input("\nEnter choice (1-2): ").strip()
        
        if choice == "2":
            print("\nGoodbye! 👋\n")
            break
        elif choice != "1":
            print("Invalid choice. Please enter 1 or 2.")
            continue
        
        # Get search term
        search_term = input("\n🔍 Enter item to search (e.g., 'iPhone 13 Pro 128GB'): ").strip()
        if not search_term:
            print("Search term cannot be empty.")
            continue
        
        # Get number of items
        n_items_str = input("📊 Number of items to analyze [default: 100]: ").strip()
        n_items = 100
        if n_items_str:
            try:
                n_items = int(n_items_str)
                if n_items < 10:
                    print("Minimum 10 items required. Using 10.")
                    n_items = 10
                elif n_items > 240:
                    print("Maximum 240 items. Using 240.")
                    n_items = 240
            except ValueError:
                print("Invalid number. Using default (100).")
                n_items = 100
        
        # Get excluded keywords
        exclude_str = input("🚫 Keywords to exclude (space-separated, or press Enter to skip): ").strip()
        excluded_keywords = exclude_str.split() if exclude_str else None
        
        # Run the search
        print(f"\n⏳ Searching eBay for '{search_term}'...")
        print(f"   Analyzing {n_items} most recently sold items...\n")
        
        stats = get_sold_item_stats(
            search_term=search_term,
            n_items=n_items,
            excluded_keywords=excluded_keywords,
            headless=True,
        )
        
        if stats:
            print(stats)
            
            # Ask if user wants to evaluate a price
            while True:
                price_str = input("\n💵 Enter a price to evaluate (or press Enter to skip): $").strip()
                if not price_str:
                    break
                try:
                    price = float(price_str)
                    assessment = stats.get_deal_assessment(price)
                    print(f"\n   {assessment}")
                except ValueError:
                    print("Invalid price. Please enter a number.")
        else:
            print("❌ Failed to retrieve data. eBay may be blocking requests.")
            print("   Try again in a few minutes.\n")


if __name__ == "__main__":
    import sys
    
    # If arguments provided, use CLI mode; otherwise interactive
    if len(sys.argv) > 1:
        import argparse
        
        parser = argparse.ArgumentParser(
            description="Analyze eBay sold items to find fair market prices"
        )
        parser.add_argument(
            "search_term",
            type=str,
            help="Item to search for (e.g., 'iPhone 13 Pro 128GB')",
        )
        parser.add_argument(
            "-n", "--num-items",
            type=int,
            default=100,
            help="Number of sold items to analyze (default: 100)",
        )
        parser.add_argument(
            "-e", "--exclude",
            type=str,
            nargs="*",
            help="Keywords to exclude (e.g., -e broken parts locked)",
        )
        parser.add_argument(
            "--visible",
            action="store_true",
            help="Show browser window (default: headless)",
        )
        parser.add_argument(
            "-p", "--price",
            type=float,
            help="Price to evaluate as a deal",
        )
        
        args = parser.parse_args()
        
        print(f"\n🔍 Searching eBay for: {args.search_term}")
        print(f"   Analyzing {args.num_items} most recently sold items...\n")
        
        stats = get_sold_item_stats(
            search_term=args.search_term,
            n_items=args.num_items,
            excluded_keywords=args.exclude,
            headless=not args.visible,
        )
        
        if stats:
            print(stats)
            
            if args.price:
                assessment = stats.get_deal_assessment(args.price)
                print(f"\n💵 Price Evaluation for ${args.price:.2f}:")
                print(f"   {assessment}\n")
        else:
            print("❌ Failed to retrieve data. Try again or use --visible to debug.")
    else:
        # No arguments - run interactive mode
        interactive_mode()
