"""
eBay Price Analyzer

Fetches active listings from eBay using the Browse API and calculates price statistics
to help determine fair market value and identify good deals.

Uses eBay Browse API (OAuth 2.0) - returns active listings only, not sold items.
"""

import statistics
import os
import json
from dataclasses import dataclass
from typing import Optional, List, Tuple
import time

import requests

from src.utils.colored_logger import setup_colored_logger, log_error_short

logger = setup_colored_logger("ebay_scraper")
VALID_CONDITION_IDS = {1000, 3000}
EBAY_APP_ID = os.environ.get("EBAY_APP_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")

# Default number of eBay listings to fetch for price comparison
DEFAULT_EBAY_ITEMS = 50


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
    SEARCH_BY_IMAGE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search_by_image"
    GET_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"
    
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

    def _build_filters_and_marketplace(
        self, browse_api_parameters: Optional[dict]
    ) -> Tuple[List[str], str]:
        """
        Build filter list and marketplace from Browse API parameters.

        Returns (filters, api_marketplace). Used by both keyword search and search_by_image.
        """
        api_filter = None
        api_marketplace = "EBAY_US"
        if browse_api_parameters:
            api_filter = browse_api_parameters.get("filter")
            api_marketplace = browse_api_parameters.get("marketplace", "EBAY_US")
        filters: List[str] = []
        if api_filter:
            if isinstance(api_filter, dict):
                filter_parts = []
                if "conditionIds" in api_filter:
                    condition_ids = api_filter.get("conditionIds") or []
                    valid_ids = [c for c in condition_ids if c in VALID_CONDITION_IDS]
                    if valid_ids:
                        filter_parts.append(f"conditionIds:{{{'|'.join(str(c) for c in valid_ids)}}}")
                api_filter = ",".join(filter_parts) if filter_parts else None
            if api_filter and isinstance(api_filter, str):
                for filter_str in [f.strip() for f in api_filter.split(",")]:
                    if filter_str.startswith("conditionIds:"):
                        try:
                            ids_part = filter_str.split(":", 1)[1].strip("{}")
                            condition_ids = [int(x.strip()) for x in ids_part.split("|")]
                            valid_ids = [c for c in condition_ids if c in VALID_CONDITION_IDS]
                            if valid_ids:
                                filters.append(f"conditionIds:{{{'|'.join(str(c) for c in valid_ids)}}}")
                        except (ValueError, IndexError):
                            pass
                    else:
                        filters.append(filter_str)
        if not filters:
            filters = [
                "buyingOptions:{FIXED_PRICE}",
                "itemCondition:{NEW|NEW_OTHER|NEW_WITH_DEFECTS|CERTIFIED_REFURBISHED|EXCELLENT_REFURBISHED|VERY_GOOD_REFURBISHED|USED}",
            ]
        else:
            if not any("buyingOptions:" in f for f in filters):
                filters.insert(0, "buyingOptions:{FIXED_PRICE}")
        return (filters, api_marketplace)

    def search_active_listings(
        self,
        keywords: str,
        max_items: int = 100,
        browse_api_parameters: Optional[dict] = None,
    ) -> Optional[List[dict]]:
        """
        Search for active eBay listings using Browse API. Returns ACTIVE listings
        only (not sold items). Supports price filters and Browse API parameters.
        
        Args:
            keywords: Search keywords
            max_items: Maximum number of items to fetch
            browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
        """
        token = self._get_access_token()
        if not token:
            return None

        filters, api_marketplace = self._build_filters_and_marketplace(browse_api_parameters)
        api_sort = (browse_api_parameters or {}).get("sort")
        logger.debug("   eBay filters: %s, sort: %s", ",".join(filters) if filters else "defaults", api_sort)

        all_items = []
        offset = 0
        search_query = keywords

        while len(all_items) < max_items:
            remaining = max_items - len(all_items)
            limit = min(200, remaining)

            params = {
                "q": search_query,
                "limit": str(limit),
                "offset": str(offset),
            }
            if api_sort:
                params["sort"] = api_sort
            if filters:
                params["filter"] = ",".join(filters)
                logger.debug("   eBay filters: %s", params["filter"])

            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": api_marketplace,
            }
            
            try:
                logger.debug(f"   eBay request: offset {offset}, limit {limit}")
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
                                "itemId": item.get("itemId", ""),
                            })
                    except (KeyError, ValueError, TypeError):
                        continue
                
                logger.debug(f"   eBay: {len(items)} this page ({len(all_items)} total)")
                
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

    def search_by_image(
        self,
        image_base64: str,
        max_items: int = 100,
        browse_api_parameters: Optional[dict] = None,
    ) -> Optional[List[dict]]:
        """
        Search for eBay listings by image using the Browse API search_by_image endpoint.

        Sends the image as Base64 in the request body. Uses the same filters and
        marketplace as keyword search. Returns the same item shape as search_active_listings
        (title, price, url, itemId) for compatibility with get_active_listing_stats.
        """
        token = self._get_access_token()
        if not token:
            return None

        filters, api_marketplace = self._build_filters_and_marketplace(browse_api_parameters)
        logger.debug("   eBay search by image, filters: %s", ",".join(filters) if filters else "defaults")

        all_items = []
        offset = 0

        while len(all_items) < max_items:
            remaining = max_items - len(all_items)
            limit = min(200, remaining)

            params = {"limit": str(limit), "offset": str(offset)}
            if filters:
                params["filter"] = ",".join(filters)

            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": api_marketplace,
                "Content-Type": "application/json",
            }
            body = {"image": image_base64}

            try:
                response = requests.post(
                    self.SEARCH_BY_IMAGE_URL,
                    params=params,
                    headers=headers,
                    json=body,
                    timeout=60,
                )
                if response.status_code == 401:
                    self._access_token = None
                    token = self._get_access_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                        response = requests.post(
                            self.SEARCH_BY_IMAGE_URL,
                            params=params,
                            headers=headers,
                            json=body,
                            timeout=60,
                        )
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                logger.debug("eBay search by image request failed: %s", e)
                break

            items = data.get("itemSummaries", [])
            if not items:
                break

            for item in items:
                try:
                    price_obj = item.get("price", {})
                    if not isinstance(price_obj, dict):
                        continue
                    price_value = float(price_obj.get("value", 0))
                    currency = price_obj.get("currency", "USD")
                    if currency != "USD" or price_value <= 0:
                        continue
                    all_items.append({
                        "title": item.get("title", ""),
                        "price": price_value,
                        "url": item.get("itemWebUrl", ""),
                        "itemId": item.get("itemId", ""),
                    })
                except (KeyError, ValueError, TypeError):
                    continue

            total = data.get("total", 0)
            if offset + len(items) >= total or len(all_items) >= max_items:
                break
            offset += len(items)
            time.sleep(0.5)

        return all_items[:max_items] if all_items else None

    def get_item_details(self, item_id: str, marketplace: str = "EBAY_US") -> Optional[dict]:
        """
        Fetch detailed item information using eBay Browse API getItem endpoint.
        
        Args:
            item_id: eBay item ID in format v1|#|#
            marketplace: Marketplace ID (default: EBAY_US)
        
        Returns:
            Dictionary with detailed item information or None if failed
        """
        token = self._get_access_token()
        if not token:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace,
        }
        
        try:
            url = f"{self.GET_ITEM_URL}/{item_id}"
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 401:
                # Token expired, refresh and retry once
                self._access_token = None
                token = self._get_access_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    response = requests.get(url, headers=headers, timeout=30)
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to fetch item details for {item_id}: {e}")
            return None
    
    def enhance_items_with_details(
        self,
        items: List[dict],
        marketplace: str = "EBAY_US",
    ) -> List[dict]:
        """
        Enhance item summaries with detailed information from getItem API.
        
        Fetches detailed information for each item and merges it into the item dict.
        Adds fields like description, condition, seller info, etc.
        
        Args:
            items: List of item dicts with at least itemId field
            marketplace: Marketplace ID (default: EBAY_US)
        
        Returns:
            List of enhanced item dicts with additional fields from getItem
        """
        enhanced_items = []
        success_count = 0
        
        for idx, item in enumerate(items):
            item_id = item.get("itemId")
            if not item_id:
                enhanced_items.append({
                    "title": item.get("title", ""),
                    "price": item.get("price", 0),
                    "url": item.get("url", ""),
                })
                continue

            details = self.get_item_details(item_id, marketplace)
            if details:
                enhanced_item = {
                    "title": item.get("title", ""),
                    "price": item.get("price", 0),
                    "url": item.get("url", ""),
                    "description": details.get("shortDescription", ""),
                    "condition": details.get("condition", ""),
                }
                enhanced_items.append(enhanced_item)
                success_count += 1
            else:
                enhanced_items.append({
                    "title": item.get("title", ""),
                    "price": item.get("price", 0),
                    "url": item.get("url", ""),
                })
        
        if success_count < len(items):
            logger.debug(f"Successfully enhanced {success_count}/{len(items)} items with getItem details")
        
        return enhanced_items
    
    def get_active_listing_stats(
        self,
        search_term: str,
        n_items: int = 100,
        browse_api_parameters: Optional[dict] = None,
        image_base64: Optional[str] = None,
    ) -> Optional[PriceStats]:
        """
        Get average price from active eBay listings using Browse API.

        When image_base64 is provided, uses search_by_image; otherwise uses keyword search.
        Returns PriceStats with average and raw prices, or None if insufficient data.

        Args:
            search_term: eBay search query (used for keyword search and for PriceStats label)
            n_items: Maximum number of items to fetch
            browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
            image_base64: Optional Base64-encoded image for search_by_image (takes precedence over search_term for the API call)
        """
        if image_base64:
            logger.debug("eBay search by image")
            items = self.search_by_image(
                image_base64=image_base64,
                max_items=n_items,
                browse_api_parameters=browse_api_parameters,
            )
        else:
            logger.debug("eBay search: '%s'", search_term)
            items = self.search_active_listings(
                keywords=search_term,
                max_items=n_items,
                browse_api_parameters=browse_api_parameters,
            )
        if not items:
            logger.warning("No eBay results for '%s'", search_term if not image_base64 else "image search")
            return None
        
        valid_items = [item for item in items if item.get("price", 0) > 0]
        
        # Enhance items with detailed information from getItem API
        api_marketplace = browse_api_parameters.get("marketplace", "EBAY_US") if browse_api_parameters else "EBAY_US"
        logger.debug(f"eBay: fetching details for {len(valid_items)} items")
        enhanced_items = self.enhance_items_with_details(valid_items, marketplace=api_marketplace)
        logger.debug(f"eBay: {len(enhanced_items)} items with details")
        
        prices = [item["price"] for item in enhanced_items]
        
        # Preserve all enhanced fields for filtering, but keep core fields for UI compatibility
        item_summaries = []
        for item in enhanced_items:
            item_summary = {
                "title": item.get("title", ""),
                "price": item["price"],
                "url": item.get("url", ""),
            }
            # Add enhanced fields if available (for filtering)
            if "description" in item:
                item_summary["description"] = item.get("description", "")
            if "condition" in item:
                item_summary["condition"] = item.get("condition", "")
            item_summaries.append(item_summary)
        
        if len(prices) < 3:
            logger.warning(f"Too few eBay results ({len(prices)}; need at least 3 to compare)")
            avg_price = statistics.mean(prices) if prices else 0.0
            stats = PriceStats(
                search_term=search_term,
                sample_size=len(prices),
                average=avg_price,
                raw_prices=sorted(prices),
                item_summaries=item_summaries,
            )
            return stats
        # Calculate average price
        stats = PriceStats(
            search_term=search_term,
            sample_size=len(prices),
            average=statistics.mean(prices),
            raw_prices=sorted(prices),
            item_summaries=item_summaries,
        )
        
        logger.debug(f"eBay: {stats.sample_size} listings, avg ${stats.average:.2f}")
        return stats


def get_market_price(
    search_term: str,
    n_items: int = 100,
    headless: bool = None,  # Deprecated, kept for backwards compatibility
    browse_api_parameters: Optional[dict] = None,
    image_base64: Optional[str] = None,
) -> Optional[PriceStats]:
    """
    Get average price from eBay active listings using Browse API.

    When image_base64 is provided, uses search_by_image; otherwise uses keyword search.
    Returns PriceStats or None if failed. headless is deprecated and ignored.

    Args:
        search_term: eBay search query (used when no image; also used as label for PriceStats when image is used)
        n_items: Maximum number of items to fetch
        headless: Deprecated, ignored
        browse_api_parameters: Optional dict with Browse API parameters (filter, marketplace, sort, limit)
        image_base64: Optional Base64-encoded image for search_by_image
    """
    if not EBAY_APP_ID or not EBAY_CLIENT_SECRET:
        logger.error("eBay credentials not configured")
        return None

    browse_client = EbayBrowseAPIClient()
    return browse_client.get_active_listing_stats(
        search_term=search_term,
        n_items=n_items,
        browse_api_parameters=browse_api_parameters,
        image_base64=image_base64,
    )
