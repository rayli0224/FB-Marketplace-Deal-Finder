"""Shared formatting for FB listings in prompts."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scrapers.fb_marketplace_scraper import Listing


def format_fb_listing_for_prompt(listing: "Listing") -> str:
    """Format a FB listing as text for prompts."""
    listing_text = f"Facebook Marketplace listing:\n- Title: {listing.title}\n- Price: ${listing.price:.2f}"
    if listing.location:
        listing_text += f"\n- Location: {listing.location}"
    if listing.description:
        listing_text += f"\n- Description: {listing.description}"
    return listing_text
