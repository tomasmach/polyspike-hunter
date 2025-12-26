"""
Market selection logic for monitoring.
Filters and selects which markets to track based on volume, themes, etc.
"""

from typing import List, Dict, Any, Optional, Tuple
import random
import structlog
from enum import Enum

logger = structlog.get_logger(__name__)


class SelectionStrategy(Enum):
    """Market selection strategies."""
    VOLUME = "volume"
    RANDOM = "random"
    MANUAL = "manual"


class MarketSelector:
    """
    Selects which markets to monitor based on configured strategy.
    """
    
    def __init__(
        self,
        strategy: SelectionStrategy = SelectionStrategy.VOLUME,
        max_markets: int = 50,
        min_volume: float = 1000.0,
        manual_token_ids: Optional[List[str]] = None,
    ):
        """
        Initialize market selector.
        
        Args:
            strategy: Selection strategy to use
            max_markets: Maximum number of markets to monitor
            min_volume: Minimum 24h volume filter (for VOLUME strategy)
            manual_token_ids: Specific token IDs to monitor (for MANUAL strategy)
        """
        self.strategy = strategy
        self.max_markets = max_markets
        self.min_volume = min_volume
        self.manual_token_ids = manual_token_ids or []
        
        logger.info(
            "market_selector_initialized",
            strategy=strategy.value,
            max_markets=max_markets,
            min_volume=min_volume
        )
    
    def select_markets(self, all_markets: List[Dict[str, Any]]) -> List[str]:
        """
        Select markets to monitor based on strategy.
        
        Args:
            all_markets: List of all available markets from API
            
        Returns:
            List of token IDs to monitor
        """
        if self.strategy == SelectionStrategy.MANUAL:
            return self._select_manual()
        elif self.strategy == SelectionStrategy.RANDOM:
            return self._select_random(all_markets)
        else:  # VOLUME
            return self._select_by_volume(all_markets)
    
    def _select_manual(self) -> List[str]:
        """Select manually configured token IDs."""
        selected = self.manual_token_ids[:self.max_markets]
        logger.info(
            "markets_selected_manual",
            count=len(selected)
        )
        return selected
    
    def _select_random(self, all_markets: List[Dict[str, Any]]) -> List[str]:
        """Select random active markets."""
        # Extract active markets with tokens
        active_markets = []
        for market in all_markets:
            if not market.get("active", False):
                continue
            
            tokens = market.get("tokens", [])
            for token in tokens:
                token_id = token.get("token_id")
                if token_id:
                    active_markets.append(token_id)
        
        # Random sample
        sample_size = min(self.max_markets, len(active_markets))
        selected = random.sample(active_markets, sample_size)
        
        logger.info(
            "markets_selected_random",
            count=len(selected),
            total_available=len(active_markets)
        )
        return selected
    
    def _select_by_volume(self, all_markets: List[Dict[str, Any]]) -> List[str]:
        """Select markets by highest 24h volume."""
        # Build list of (token_id, volume) pairs
        market_volumes: List[Tuple[str, float]] = []
        
        active_count = 0
        
        for market in all_markets:
            if not market.get("active", False):
                continue
            
            active_count += 1
            
            # Get volume - try multiple fields
            volume = float(market.get("volume", 0) or market.get("volume24hr", 0) or 0)
            
            tokens = market.get("tokens", [])
            for token in tokens:
                token_id = token.get("token_id")
                if token_id:
                    market_volumes.append((token_id, volume))
        
        logger.info(
            "market_scan_stats",
            total_markets=len(all_markets),
            active_markets=active_count,
            total_tokens=len(market_volumes)
        )
        
        # Sort by volume descending
        market_volumes.sort(key=lambda x: x[1], reverse=True)
        
        # If we have markets but none meet volume threshold, just take top N anyway
        if len(market_volumes) > 0:
            # Filter by min volume first if min_volume > 0
            if self.min_volume > 0:
                filtered = [(t, v) for t, v in market_volumes if v >= self.min_volume]
            else:
                # If min_volume is 0, take all markets
                filtered = market_volumes
            
            if len(filtered) == 0:
                # No markets meet volume threshold, take top N regardless
                logger.warning(
                    "no_markets_meet_volume_threshold",
                    min_volume=self.min_volume,
                    using_top_markets=self.max_markets,
                    message="Taking markets regardless of volume"
                )
                selected = [token_id for token_id, _ in market_volumes[:self.max_markets]]
            else:
                # Use filtered markets
                selected = [token_id for token_id, _ in filtered[:self.max_markets]]
                logger.info(
                    "using_filtered_markets",
                    filtered_count=len(filtered),
                    selected_count=len(selected)
                )
        else:
            selected = []
        
        logger.info(
            "markets_selected_by_volume",
            count=len(selected),
            min_volume=self.min_volume,
            total_candidates=len(market_volumes)
        )
        
        return selected
