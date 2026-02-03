"""
eBay Sold Items Price Analyzer

Fetches item prices from eBay using the official API and calculates 
price statistics to help determine fair market value and identify good deals.

Requires eBay API credentials from https://developer.ebay.com

Author: Auto-generated
"""

import time
import statistics
import base64
import os
from dataclasses import dataclass
from typing import Optional
import logging

# Third-party imports
import requests
import numpy as np

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
📊 eBay Price Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Search Term: {self.search_term}
Sample Size: {self.sample_size} items

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


class EbayAPI:
    """
    eBay Official API client for searching items.
    
    To get API credentials:
    1. Go to https://developer.ebay.com
    2. Create an account and app
    3. Get your App ID (Client ID) and Cert ID (Client Secret)
    4. Set environment variables: EBAY_CLIENT_ID and EBAY_CLIENT_SECRET
    
    Note: The Browse API shows active listings. For sold items, you need
    Marketplace Insights API access (requires eBay approval).
    """
    
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    MARKETPLACE_INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
    
    def __init__(self, client_id: str = None, client_secret: str = None):
        """
        Initialize the eBay API client.
        
        Args:
            client_id: eBay App ID (or set EBAY_CLIENT_ID env var)
            client_secret: eBay Cert ID (or set EBAY_CLIENT_SECRET env var)
        """
        self.client_id = client_id or os.environ.get("EBAY_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("EBAY_CLIENT_SECRET")
        self._access_token = None
        self._token_expiry = 0
        
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "eBay API credentials required. Set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET "
                "environment variables or pass them to the constructor.\n"
                "Get credentials at: https://developer.ebay.com"
            )
    
    def _get_access_token(self) -> str:
        """Get or refresh the OAuth access token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        }
        
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope https://api.ebay.com/oauth/api_scope/buy.marketplace.insights",
        }
        
        response = requests.post(self.TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        self._access_token = token_data["access_token"]
        self._token_expiry = time.time() + token_data.get("expires_in", 7200) - 60
        
        return self._access_token
    
    def search_sold_items(self, search_term: str, limit: int = 100) -> Optional[PriceStats]:
        """
        Search for sold/completed items using Marketplace Insights API.
        
        Note: Requires Marketplace Insights API access (need eBay approval).
        Falls back to Browse API (active listings) if not approved.
        
        Args:
            search_term: Item to search for
            limit: Max number of results
            
        Returns:
            PriceStats object or None if failed
        """
        try:
            token = self._get_access_token()
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            
            # Try Marketplace Insights API (sold items)
            params = {
                "q": search_term,
                "limit": min(limit, 200),
                "sort": "-endDate",  # Most recent first
            }
            
            logger.info(f"Searching Marketplace Insights API for: {search_term}")
            response = requests.get(
                self.MARKETPLACE_INSIGHTS_URL,
                headers=headers,
                params=params,
            )
            
            if response.status_code == 403:
                logger.warning("Marketplace Insights API access denied. Falling back to Browse API.")
                return self._search_browse_api(search_term, limit, headers)
            
            response.raise_for_status()
            data = response.json()
            
            items = data.get("itemSales", [])
            if not items:
                logger.warning("No sold items found, trying Browse API")
                return self._search_browse_api(search_term, limit, headers)
            
            prices = []
            for item in items:
                try:
                    price = float(item.get("lastSoldPrice", {}).get("value", 0))
                    if price > 0:
                        prices.append(price)
                except (ValueError, TypeError):
                    continue
            
            return self._calculate_stats(search_term, prices)
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"eBay API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
    
    def _search_browse_api(self, search_term: str, limit: int, headers: dict) -> Optional[PriceStats]:
        """Search using Browse API (active listings, not sold)."""
        logger.info("Using Browse API (active listings)")
        
        params = {
            "q": search_term,
            "limit": min(limit, 200),
            "sort": "price",
        }
        
        response = requests.get(self.BROWSE_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        items = data.get("itemSummaries", [])
        if not items:
            logger.warning("No items found")
            return None
        
        prices = []
        for item in items:
            try:
                price = float(item.get("price", {}).get("value", 0))
                if price > 0:
                    prices.append(price)
            except (ValueError, TypeError):
                continue
        
        stats = self._calculate_stats(search_term, prices)
        if stats:
            logger.info("Note: These are ACTIVE listing prices, not sold prices")
        return stats
    
    def search_active_listings(self, search_term: str, limit: int = 100) -> Optional[PriceStats]:
        """
        Search for active listings using Browse API.
        
        Args:
            search_term: Item to search for
            limit: Max number of results
            
        Returns:
            PriceStats object or None if failed
        """
        try:
            token = self._get_access_token()
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            
            return self._search_browse_api(search_term, limit, headers)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
    
    def _calculate_stats(self, search_term: str, prices: list[float]) -> Optional[PriceStats]:
        """Calculate statistics from price list."""
        if len(prices) < 3:
            logger.error(f"Not enough data: only {len(prices)} prices found")
            return None
        
        return PriceStats(
            search_term=search_term,
            sample_size=len(prices),
            average=statistics.mean(prices),
            median=statistics.median(prices),
            min_price=min(prices),
            max_price=max(prices),
            std_dev=statistics.stdev(prices) if len(prices) > 1 else 0,
            percentile_25=float(np.percentile(prices, 25)),
            percentile_75=float(np.percentile(prices, 75)),
            raw_prices=sorted(prices),
        )


def get_price_stats(
    search_term: str,
    n_items: int = 100,
) -> Optional[PriceStats]:
    """
    Get price statistics from eBay.
    
    Requires EBAY_CLIENT_ID and EBAY_CLIENT_SECRET environment variables.
    
    Args:
        search_term: The item to search for (e.g., "iPhone 13 Pro 128GB")
        n_items: Number of items to analyze (max 200)
        
    Returns:
        PriceStats object with price analysis, or None if failed
        
    Example:
        >>> stats = get_price_stats("Nintendo Switch OLED", n_items=50)
        >>> print(stats)
        >>> print(stats.get_deal_assessment(280.00))
    """
    api = EbayAPI()
    return api.search_sold_items(search_term, limit=n_items)


# =============================================================================
# Interactive CLI
# =============================================================================

def interactive_mode():
    """Run in interactive command-line mode."""
    print("\n" + "=" * 55)
    print("  eBay Price Analyzer - Interactive Mode")
    print("=" * 55)
    
    # Check for API credentials
    has_api = bool(os.environ.get("EBAY_CLIENT_ID") and os.environ.get("EBAY_CLIENT_SECRET"))
    if has_api:
        print("\n✅ eBay API credentials found")
    else:
        print("\n❌ eBay API credentials NOT found")
        print("\nTo use this tool, you need eBay API credentials:")
        print("1. Go to https://developer.ebay.com")
        print("2. Create an account and application")
        print("3. Get your App ID (Client ID) and Cert ID (Client Secret)")
        print("4. Set environment variables:")
        print("   export EBAY_CLIENT_ID='your-client-id'")
        print("   export EBAY_CLIENT_SECRET='your-client-secret'")
        print("\nThen run this script again.")
        return
    
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
                    print("Minimum 10 items. Using 10.")
                    n_items = 10
                elif n_items > 200:
                    print("Maximum 200 items. Using 200.")
                    n_items = 200
            except ValueError:
                print("Invalid number. Using default (100).")
                n_items = 100
        
        # Run the search
        print(f"\n⏳ Searching eBay for '{search_term}'...")
        print(f"   Analyzing up to {n_items} items...\n")
        
        try:
            stats = get_price_stats(search_term=search_term, n_items=n_items)
            
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
                print("❌ No results found. Try a different search term.")
        except ValueError as e:
            print(f"❌ {e}")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    import sys
    
    # If arguments provided, use CLI mode; otherwise interactive
    if len(sys.argv) > 1:
        import argparse
        
        parser = argparse.ArgumentParser(
            description="Analyze eBay prices to find fair market value"
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
            help="Number of items to analyze (default: 100, max: 200)",
        )
        parser.add_argument(
            "-p", "--price",
            type=float,
            help="Price to evaluate as a deal",
        )
        
        args = parser.parse_args()
        
        print(f"\n🔍 Searching eBay for: {args.search_term}")
        print(f"   Analyzing up to {args.num_items} items...\n")
        
        try:
            stats = get_price_stats(
                search_term=args.search_term,
                n_items=args.num_items,
            )
            
            if stats:
                print(stats)
                
                if args.price:
                    assessment = stats.get_deal_assessment(args.price)
                    print(f"\n💵 Price Evaluation for ${args.price:.2f}:")
                    print(f"   {assessment}\n")
            else:
                print("❌ No results found. Try a different search term.")
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(1)
    else:
        # No arguments - run interactive mode
        interactive_mode()
