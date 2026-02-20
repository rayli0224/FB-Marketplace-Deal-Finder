"""
eBay query generation — produces optimized eBay search queries from product recon data.

Takes structured product intelligence (from internet enrichment) and generates
an effective eBay search string.
"""

import os
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from src.utils.colored_logger import setup_colored_logger, log_error_short, truncate_lines
from src.evaluation.ebay_query_generator.prompts import SYSTEM_MESSAGE, get_query_generation_prompt
from src.evaluation.openai_client import create_sync_response, extract_response_output_text, try_parse_json_dict

logger = setup_colored_logger("ebay_query_generator")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
QUERY_GENERATION_MAX_OUTPUT_TOKENS = 1000


def generate_ebay_query(product_recon_json: str, original_query: str) -> Optional[str]:
    """
    Generate an eBay search query from structured product recon.

    Returns the enhanced query string, or None on failure.
    Uses original_query as fallback when the model omits enhanced_query.
    """
    if not OpenAI or not OPENAI_API_KEY:
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = get_query_generation_prompt(product_recon_json)

    try:
        response = create_sync_response(
            client,
            instructions=SYSTEM_MESSAGE,
            prompt=prompt,
            max_output_tokens=QUERY_GENERATION_MAX_OUTPUT_TOKENS,
        )
        raw_content = extract_response_output_text(response)
        try:
            truncated_content = truncate_lines(raw_content, 5)
            logger.debug(f"eBay search suggestion (preview):\n\t{truncated_content}")
        except Exception:
            pass  # Preview is optional; log on failure only if needed

        result = try_parse_json_dict(raw_content)
        if result is None:
            log_error_short(logger, "Search suggestion response was invalid JSON")
            logger.debug(f"Response content: {raw_content}")
            return None

        enhanced_query = result.get("enhanced_query", original_query)
        logger.debug(f"Search: '{enhanced_query}'")
        return enhanced_query
    except Exception as e:
        log_error_short(logger, f"Search suggestion request failed: {e}")
        return None
