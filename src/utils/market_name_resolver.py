"""
Market name resolver for token_id to readable name mapping.
Fetches and caches market questions for human-readable output.
"""

import asyncio
from typing import Dict, List, Optional
import threading
import structlog

from src.core.client import PolymarketClient

logger = structlog.get_logger(__name__)


class MarketNameResolver:
    """
    Resolves token IDs to readable market names with caching.
    Thread-safe with fallback to truncated token IDs.
    """

    def __init__(self, client: PolymarketClient):
        """
        Initialize market name resolver.

        Args:
            client: Polymarket client for fetching market data
        """
        self.client = client
        self._cache: Dict[str, str] = {}
        self._lock = threading.RLock()
        logger.info("market_name_resolver_initialized")

    async def initialize(self, token_ids: List[str]) -> None:
        """
        Fetch and cache market names for given token IDs.

        Args:
            token_ids: List of token IDs to resolve
        """
        logger.info(
            "initializing_market_names",
            token_count=len(token_ids)
        )

        try:
            # Fetch all markets with pagination
            all_markets = []
            next_cursor = None
            page_count = 0

            while True:
                try:
                    markets_data = await self.client.get_markets(next_cursor=next_cursor)
                    markets = markets_data.get("data", [])
                    all_markets.extend(markets)
                    page_count += 1

                    # Check for next cursor
                    next_cursor = markets_data.get("next_cursor")

                    if not next_cursor:
                        break

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning(
                        "failed_to_fetch_markets_page",
                        page=page_count,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    # Continue with what we have
                    break

            # Build token_id -> question mapping from all pages
            token_to_question: Dict[str, str] = {}

            for market in all_markets:
                tokens = market.get("tokens", [])
                question = market.get("question") or market.get("id") or market.get("slug", "Unknown Market")

                for token in tokens:
                    token_id = token.get("token_id")
                    if token_id:
                        token_to_question[token_id] = question

            # Cache only the requested tokens
            with self._lock:
                for token_id in token_ids:
                    if token_id in token_to_question:
                        self._cache[token_id] = token_to_question[token_id]
                    else:
                        # Token not found in markets - use fallback
                        self._cache[token_id] = self._truncate_token(token_id)

            cached_count = sum(1 for tid in token_ids if self._cache.get(tid) != self._truncate_token(tid))
            logger.info(
                "market_names_cached",
                cached_count=cached_count,
                total_requested=len(token_ids),
                fallback_count=len(token_ids) - cached_count,
                pages_fetched=page_count,
                total_markets=len(all_markets)
            )

        except Exception as e:
            logger.error(
                "failed_to_initialize_market_names",
                error=str(e),
                error_type=type(e).__name__,
                using_fallback=True
            )

            # Fallback: cache all token IDs as truncated
            with self._lock:
                for token_id in token_ids:
                    self._cache[token_id] = self._truncate_token(token_id)

    def get_name(self, token_id: str) -> str:
        """
        Get market name for token ID.

        Args:
            token_id: Token ID to resolve

        Returns:
            Market question string

        Raises:
            KeyError: If token_id not found in cache
        """
        with self._lock:
            if token_id in self._cache:
                return self._cache[token_id]
            raise KeyError(f"Token ID not in cache: {token_id}")

    def get_name_safe(self, token_id: str) -> str:
        """
        Get market name for token ID with fallback. Never raises.

        Args:
            token_id: Token ID to resolve

        Returns:
            Market question string or truncated token ID if not found
        """
        with self._lock:
            if token_id in self._cache:
                return self._cache[token_id]

        # Cache miss - return fallback and log
        logger.debug(
            "market_name_cache_miss",
            token_id=token_id,
            using_fallback=True
        )
        return self._truncate_token(token_id)

    def _truncate_token(self, token_id: str) -> str:
        """
        Truncate token ID to readable length.

        Args:
            token_id: Full token ID

        Returns:
            Truncated token ID string
        """
        if len(token_id) > 16:
            return f"{token_id[:16]}..."
        return token_id

    @property
    def cache_size(self) -> int:
        """Get number of cached entries."""
        with self._lock:
            return len(self._cache)
