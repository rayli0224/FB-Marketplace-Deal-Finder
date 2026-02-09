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
import time

import requests

from src.utils.colored_logger import setup_colored_logger, log_error_short

logger = setup_colored_logger("ebay_scraper")
VALID_CONDITION_IDS = {1000, 3000}
EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")


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
        """Initialize with app_id and client_secret, or from EBAY_APP_ID and EBAY_CLIENT_SECRET env if not provided."""
        self.app_id = app_id or EBAY_APP_ID
        self.client_secret = client_secret or EBAY_CLIENT_SECRET
        self._access_token = None
        self._token_expiry = 0

    def _get_access_token(self) -> Optional[str]:
        """Get or refresh OAuth 2.0 access token using Client Credentials flow."""
        import base64
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        
        if not self.app_id or not self.client_secret:
            logger.error("eBay credentials missing")
            return None
        
        try:
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
            
        except requests.exceptions.RequestException:
            return None
    
    def search_active_listings(
        self,
        keywords: str,
        max_items: int = 100,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        browse_api_parameters: Optional[dict] = None,
    ) -> Optional[List[dict]]:
        """
        Search for active eBay listings using Browse API. Returns ACTIVE listings
        only (not sold items). Supports price filters and Browse API parameters.
        
        Args:
            keywords: Search keywords
            max_items: Maximum number of items to fetch
            min_price: Optional minimum price filter
            max_price: Optional maximum price filter
            browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
        """
        token = self._get_access_token()
        if not token:
            return None
        
        all_items = []
        offset = 0
        
        # Extract Browse API parameters if provided
        api_filter = None
        api_marketplace = "EBAY_US"  # Default
        api_sort = None
        api_limit_override = None
        
        if browse_api_parameters:
            api_filter = browse_api_parameters.get("filter")
            api_marketplace = browse_api_parameters.get("marketplace", "EBAY_US")
            api_sort = browse_api_parameters.get("sort")
            api_limit_override = browse_api_parameters.get("limit")
            logger.info(f"   Using Browse API parameters:")
            if api_filter:
                logger.info(f"      Filter: {api_filter}")
            if api_marketplace:
                logger.info(f"      Marketplace: {api_marketplace}")
            if api_sort:
                logger.info(f"      Sort: {api_sort}")
            if api_limit_override:
                logger.info(f"      Limit (page size): {api_limit_override}")
        else:
            logger.debug("   No Browse API parameters provided, using defaults")
        
        # Use keywords directly as search query (eBay API doesn't support exclusion syntax)
        search_query = keywords
        
        while len(all_items) < max_items:
            # Calculate how many items we still need
            remaining = max_items - len(all_items)
            # Use API-provided limit as page size if available, otherwise use calculated limit
            # The limit is the page size (items per request), not the total limit
            if api_limit_override:
                page_size = min(int(api_limit_override), 200)  # API max is 200 per page
                limit = min(page_size, remaining)
            else:
                limit = min(200, remaining)  # API max is 200 per page
            
            params = {
                "q": search_query,
                "limit": str(limit),
                "offset": str(offset),
            }
            
            # Add sort if provided
            if api_sort:
                params["sort"] = api_sort
            
            # Build filter list
            filters: List[str] = []
            
            # Process API-provided filter if available
            if api_filter:
                # Handle both string and dict formats
                if isinstance(api_filter, dict):
                    # Convert dict format to filter string format
                    # Example: {'conditionIds': [2000]} -> "conditionIds:{2000}"
                    # eBay Browse API uses numeric condition IDs, not string names
                    filter_parts = []
                    if "conditionIds" in api_filter:
                        condition_ids = api_filter["conditionIds"]
                        if condition_ids:
                            # Filter out invalid condition IDs
                            valid_ids = [cond_id for cond_id in condition_ids if cond_id in VALID_CONDITION_IDS]
                            invalid_ids = [cond_id for cond_id in condition_ids if cond_id not in VALID_CONDITION_IDS]
                            if invalid_ids:
                                logger.warning(f"   Removed invalid condition IDs from OpenAI response: {invalid_ids}")
                            if valid_ids:
                                # Convert list of IDs to pipe-separated string
                                id_string = "|".join(str(cond_id) for cond_id in valid_ids)
                                filter_parts.append(f"conditionIds:{{{id_string}}}")
                    api_filter = ",".join(filter_parts) if filter_parts else None
                
                # Parse the filter string and validate condition IDs
                # The API filter might be a comma-separated string or a single filter
                if api_filter and isinstance(api_filter, str):
                    api_filters = [f.strip() for f in api_filter.split(",")]
                    validated_filters = []
                    for filter_str in api_filters:
                        # Check if this is a conditionIds filter and validate it
                        if filter_str.startswith("conditionIds:"):
                            # Extract condition IDs from format like "conditionIds:{1000|2000}"
                            try:
                                # Parse conditionIds:{1000|2000} or conditionIds:{4000}
                                ids_part = filter_str.split(":", 1)[1]
                                ids_part = ids_part.strip("{}")
                                condition_ids = [int(id_str.strip()) for id_str in ids_part.split("|")]
                                
                                # Filter out invalid IDs
                                valid_ids = [cid for cid in condition_ids if cid in VALID_CONDITION_IDS]
                                invalid_ids = [cid for cid in condition_ids if cid not in VALID_CONDITION_IDS]
                                
                                if invalid_ids:
                                    logger.warning(f"   Removed invalid condition IDs from OpenAI response: {invalid_ids}")
                                
                                if valid_ids:
                                    # Reconstruct filter with only valid IDs
                                    id_string = "|".join(str(cid) for cid in valid_ids)
                                    validated_filters.append(f"conditionIds:{{{id_string}}}")
                                # If no valid IDs remain, skip this filter entirely
                            except (ValueError, IndexError) as e:
                                logger.warning(f"   Failed to parse conditionIds filter '{filter_str}': {e}, skipping")
                        else:
                            # Not a conditionIds filter, add as-is
                            validated_filters.append(filter_str)
                    
                    filters.extend(validated_filters)
            
            # Only add default filters if no API-provided filters were given
            # This allows OpenAI to have full control over filtering when it provides parameters
            if not filters:
                # Default filters: Fixed price only (no auctions) and common good conditions
                filters = [
                    "buyingOptions:{FIXED_PRICE}",
                    "itemCondition:{NEW|NEW_OTHER|NEW_WITH_DEFECTS|CERTIFIED_REFURBISHED|EXCELLENT_REFURBISHED|VERY_GOOD_REFURBISHED|USED}",
                ]
            else:
                # If OpenAI provided filters, only add buyingOptions if not already present
                # This ensures we still filter out auctions unless OpenAI explicitly wants them
                has_buying_options = any("buyingOptions:" in f for f in filters)
                if not has_buying_options:
                    filters.insert(0, "buyingOptions:{FIXED_PRICE}")
            
            if filters:
                params["filter"] = ",".join(filters)
                logger.debug(f"   Final filters: {params['filter']}")
            
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": api_marketplace,
            }
            
            try:
                logger.debug(f"   Fetching eBay Browse API (offset {offset}, limit {limit}, marketplace {api_marketplace})...")
                logger.debug(f"   Request params: {params}")
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
                
            except requests.exceptions.RequestException:
                break
        
        return all_items[:max_items] if all_items else None
    
    def get_active_listing_stats(
        self,
        search_term: str,
        n_items: int = 100,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        browse_api_parameters: Optional[dict] = None,
    ) -> Optional[PriceStats]:
        """
        Get average price from active eBay listings using Browse API.
        Returns PriceStats with average and raw prices, or None if insufficient data.
        
        Args:
            search_term: eBay search query
            n_items: Maximum number of items to fetch
            min_price: Optional minimum price filter
            max_price: Optional maximum price filter
            browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
        """
        logger.info(f"Searching eBay: '{search_term}'")
        logger.debug("Note: Browse API returns ACTIVE listings only, not sold items")
        
        items = self.search_active_listings(
            keywords=search_term,
            max_items=n_items,
            min_price=min_price,
            max_price=max_price,
            browse_api_parameters=browse_api_parameters,
        )
        if not items:
            logger.warning(f"No items found from Browse API for query: '{search_term}'")
            return None
        
        valid_items = [item for item in items if item.get("price", 0) > 0]
        prices = [item["price"] for item in valid_items]
        
        if len(prices) < 3:
            logger.warning(f"Not enough data from Browse API: only found {len(prices)} items (minimum 3 required for statistical significance)")
            item_summaries = [
                {"title": item.get("title", ""), "price": item["price"], "url": item.get("url", "")}
                for item in valid_items
            ]
            avg_price = statistics.mean(prices) if prices else 0.0
            stats = PriceStats(
                search_term=search_term,
                sample_size=len(prices),
                average=avg_price,
                raw_prices=sorted(prices),
                item_summaries=item_summaries,
            )
            return stats

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
        
        logger.info(f"Found {stats.sample_size} eBay listings, avg ${stats.average:.2f}")
        return stats


def get_market_price(
    search_term: str,
    n_items: int = 100,
    headless: bool = None,  # Deprecated, kept for backwards compatibility
    browse_api_parameters: Optional[dict] = None,
) -> Optional[PriceStats]:
    """
    Get average price from eBay active listings using Browse API. Returns PriceStats
    or None if failed. headless parameter is deprecated and ignored.
    
    Args:
        search_term: eBay search query
        n_items: Maximum number of items to fetch
        headless: Deprecated, ignored
        browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
    """
    if not EBAY_APP_ID or not EBAY_CLIENT_SECRET:
        logger.error("eBay credentials not configured")
        return None
    
    browse_client = EbayBrowseAPIClient()
    return browse_client.get_active_listing_stats(
        search_term=search_term,
        n_items=n_items,
        browse_api_parameters=browse_api_parameters,
    )
