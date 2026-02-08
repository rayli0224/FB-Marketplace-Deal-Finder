"""
eBay Price Analyzer

Fetches active listings from eBay using the Browse API and calculates price statistics
to help determine fair market value and identify good deals.

Uses eBay Browse API (OAuth 2.0) - returns active listings only, not sold items.
"""

import statistics
import os
from dataclasses import dataclass
from typing import Optional, List
import logging
import time

import requests

from src.utils.colored_logger import setup_colored_logger

# Configure colored logging with module prefix
logger = setup_colored_logger("ebay_scraper", level=logging.INFO)

# eBay API credentials (get from developer.ebay.com)
EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")

# Check credentials (only log when actually needed)


@dataclass
class PriceStats:
    """Container for price statistics results from active listings."""
    search_term: str
    sample_size: int
    average: float
    raw_prices: list[float]
    item_summaries: Optional[List[dict]] = None  # [{title, price, url}, ...] for UI transparency
    
    def __str__(self) -> str:
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 eBay Price Analysis (Active Listings)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Search Term: {self.search_term}
Sample Size: {self.sample_size} active listings

💰 Average Price: ${self.average:.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


class EbayBrowseAPIClient:
    """
    eBay Browse API client for fetching active listings.
    
    Note: This returns ACTIVE listings only (not sold items), but provides current
    market prices which can be useful for price comparison. Uses OAuth 2.0 Client
    Credentials flow for authentication.
    """
    
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    BASE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    
    def __init__(self, app_id: str = None, client_secret: str = None):
        """
        Initialize the eBay Browse API client.
        
        Args:
            app_id: eBay App ID (Client ID) from developer.ebay.com
            client_secret: eBay Client Secret from developer.ebay.com
        """
        self.app_id = app_id or EBAY_APP_ID
        self.client_secret = client_secret or EBAY_CLIENT_SECRET
        self._access_token = None
        self._token_expiry = 0
        
        if not self.app_id or not self.client_secret:
            pass
    
    def _get_access_token(self) -> Optional[str]:
        """Get or refresh OAuth 2.0 access token using Client Credentials flow."""
        import base64
        
        # Check if token is still valid
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        if not self.app_id or not self.client_secret:
            logger.error("❌ eBay credentials missing")
            return None
        
        try:
            # Create Basic auth header
            credentials = f"{self.app_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}",
            }
            
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",  # Public data scope
            }
            
            response = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 7200)
            self._token_expiry = time.time() + expires_in - 60  # Refresh 1 min early
            
            return self._access_token
            
        except requests.exceptions.RequestException as e:
            pass
            return None
    
    def search_active_listings(
        self,
        keywords: str,
        max_items: int = 100,
        excluded_keywords: Optional[List[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> Optional[List[dict]]:
        """
        Search for active eBay listings using Browse API.
        
        Note: Returns ACTIVE listings only, not sold items. Useful for current market prices.
        
        Args:
            keywords: Search keywords
            max_items: Maximum number of items to return (API limit: 200 per page)
            excluded_keywords: Keywords to exclude from search
            min_price: Minimum price filter
            max_price: Maximum price filter
            
        Returns:
            List of item dictionaries with price data, or None if failed
        """
        token = self._get_access_token()
        if not token:
            return None
        
        all_items = []
        offset = 0
        
        # Build search query with exclusions
        search_query = keywords
        if excluded_keywords:
            search_query += " -" + " -".join(excluded_keywords)
        
        while len(all_items) < max_items:
            # Calculate how many items we still need
            remaining = max_items - len(all_items)
            limit = min(200, remaining)  # API max is 200 per page
            
            params = {
                "q": search_query,
                "limit": str(limit),
                "offset": str(offset),
                # No explicit sort -> eBay default (Best Match)
            }
            
            # Build filter list:
            # - Fixed price only (no auctions)
            # - All conditions except FOR_PARTS_OR_NOT_WORKING (whitelist common good conditions)
            filters: List[str] = [
                "buyingOptions:{FIXED_PRICE}",
                "itemCondition:{NEW|NEW_OTHER|NEW_WITH_DEFECTS|CERTIFIED_REFURBISHED|EXCELLENT_REFURBISHED|VERY_GOOD_REFURBISHED|USED}",
            ]
            
            # Add price filters if specified
            if min_price is not None:
                filters.append(f"price:[{min_price}..]")
            if max_price is not None:
                filters.append(f"price:[..{max_price}]")
            
            if filters:
                params["filter"] = ",".join(filters)
            
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            }
            
            try:
                logger.debug(f"Fetching eBay Browse API (offset {offset})...")
                response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=30)
                
                if response.status_code == 401:
                    # Token expired, refresh and retry once
                    self._access_token = None
                    token = self._get_access_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=30)
                
                response.raise_for_status()
                data = response.json()
                
                # Extract items
                items = data.get("itemSummaries", [])
                if not items:
                    break
                
                # Parse items and extract prices
                for item in items:
                    try:
                        price_obj = item.get("price", {})
                        if isinstance(price_obj, dict):
                            price_value = float(price_obj.get("value", 0))
                            currency = price_obj.get("currency", "USD")
                        else:
                            continue
                        
                        # Only process USD for now
                        if currency != "USD":
                            continue
                        
                        if price_value > 0:
                            all_items.append({
                                "title": item.get("title", ""),
                                "price": price_value,
                                "url": item.get("itemWebUrl", ""),
                            })
                    except (KeyError, ValueError, TypeError):
                        continue
                
                logger.debug(f"Found {len(items)} active listings (Total: {len(all_items)}) for query: '{keywords}'")
                
                # Check if there are more pages
                total = data.get("total", 0)
                if offset + len(items) >= total or len(all_items) >= max_items:
                    break
                
                offset += len(items)
                
                # Rate limiting: be nice to the API
                time.sleep(0.5)
                
            except requests.exceptions.RequestException as e:
                pass
                break
        
        return all_items[:max_items] if all_items else None
    
    def get_active_listing_stats(
        self,
        search_term: str,
        n_items: int = 100,
        excluded_keywords: Optional[List[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> Optional[PriceStats]:
        """
        Get average price from active listings using Browse API.
        
        Note: These are ACTIVE listings, not sold items. Useful for current market comparison.
        
        Args:
            search_term: The item to search for
            n_items: Target number of listings to analyze
            excluded_keywords: Words to exclude from search
            min_price: Minimum price filter
            max_price: Maximum price filter
            
        Returns:
            PriceStats object with average price and raw prices, or None if failed
        """
        logger.info(f"🔍 Searching eBay for: '{search_term}'")
        logger.debug("Note: Browse API returns ACTIVE listings only, not sold items")
        
        items = self.search_active_listings(
            keywords=search_term,
            max_items=n_items,
            excluded_keywords=excluded_keywords,
            min_price=min_price,
            max_price=max_price,
        )
        
        if not items or len(items) < 3:
            logger.warning(f"Not enough data from Browse API: only found {len(items) if items else 0} items (minimum 3 required for statistical significance)")
            return None
        
        valid_items = [item for item in items if item.get("price", 0) > 0]
        prices = [item["price"] for item in valid_items]
        if len(prices) < 3:
            logger.error(f"⚠️  Insufficient prices - {len(prices)} valid")
            return None

        item_summaries = [
            {"title": item.get("title", ""), "price": item["price"], "url": item.get("url", "")}
            for item in valid_items
        ]
        # Calculate average price
        stats = PriceStats(
            search_term=search_term,
            sample_size=len(prices),
            average=statistics.mean(prices),
            raw_prices=sorted(prices),
            item_summaries=item_summaries,
        )
        
        logger.info(f"✅ Found {stats.sample_size} eBay listings | Avg: ${stats.average:.2f}")
        return stats


def get_market_price(
    search_term: str,
    n_items: int = 100,
    excluded_keywords: Optional[list[str]] = None,
    headless: bool = None,  # Deprecated, kept for backwards compatibility
) -> Optional[PriceStats]:
    """
    Get average price from eBay active listings using Browse API.
    
    Note: This function returns ACTIVE listings (current market prices), not sold items.
    
    Args:
        search_term: The item to search for (e.g., "iPhone 13 Pro 128GB")
        n_items: Number of listings to analyze (50-100 recommended)
        excluded_keywords: Words to exclude (e.g., ["broken", "parts", "locked"])
        headless: Deprecated parameter, kept for backwards compatibility
        
    Returns:
        PriceStats object with average price and raw prices, or None if failed
        
    Example:
        >>> stats = get_market_price("Nintendo Switch OLED", n_items=50)
        >>> print(stats)
        >>> print(f"Average price: ${stats.average:.2f}")
    """
    if not EBAY_APP_ID or not EBAY_CLIENT_SECRET:
        logger.error("❌ eBay credentials not configured")
        return None
    
    browse_client = EbayBrowseAPIClient()
    return browse_client.get_active_listing_stats(
        search_term=search_term,
        n_items=n_items,
        excluded_keywords=excluded_keywords,
    )
