"""
Price tracking and analysis for market monitoring.
Maintains rolling price history using deque for O(1) operations.
"""

from collections import deque
from typing import Optional, List
from dataclasses import dataclass
import time
import statistics
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PricePoint:
    """Single price observation."""
    price: float
    timestamp: float


class PriceTracker:
    """
    Tracks price history for a single market token.
    Uses deque for efficient O(1) append/pop operations.
    """
    
    def __init__(self, token_id: str, max_history_seconds: int = 60):
        """
        Initialize price tracker.
        
        Args:
            token_id: Token ID being tracked
            max_history_seconds: How many seconds of history to maintain
        """
        self.token_id = token_id
        self.max_history_seconds = max_history_seconds
        self._history: deque[PricePoint] = deque()
        self._last_price: Optional[float] = None
    
    def add_price(self, price: float, timestamp: Optional[float] = None) -> None:
        """
        Add new price observation.

        Args:
            price: Current price
            timestamp: Unix timestamp (defaults to now)
        """
        # Price validation
        if price is None:
            logger.error(
                "invalid_price_none",
                token_id=self.token_id,
                message="Price cannot be None - skipping"
            )
            return

        if price < 0:
            logger.error(
                "invalid_price_negative",
                token_id=self.token_id,
                price=price,
                message="Price cannot be negative - skipping"
            )
            return

        if price > 1.0:
            logger.warning(
                "unusual_price_above_one",
                token_id=self.token_id,
                price=price,
                message="Price > 1.0 is unusual for Polymarket"
            )

        # Timestamp validation
        if timestamp is None:
            timestamp = time.time()

        current_time = time.time()
        if timestamp > current_time + 60:
            logger.warning(
                "future_timestamp_detected",
                token_id=self.token_id,
                timestamp=timestamp,
                current_time=current_time,
                delta=timestamp - current_time,
                message="Timestamp is in future - adjusting to current time"
            )
            timestamp = current_time

        point = PricePoint(price=price, timestamp=timestamp)
        self._history.append(point)
        self._last_price = price

        # Deque size protection - prevent unbounded memory growth
        if len(self._history) > 10000:
            logger.warning(
                "excessive_deque_size",
                token_id=self.token_id,
                size=len(self._history),
                message="Deque exceeds 10000 entries - forcing cleanup"
            )
            # Force aggressive cleanup by removing oldest 50%
            target_size = 5000
            while len(self._history) > target_size:
                self._history.popleft()

        # Remove old data points outside our window
        self._cleanup_old_data(timestamp)
    
    def _cleanup_old_data(self, current_timestamp: float) -> None:
        """Remove price points older than max_history_seconds."""
        cutoff_time = current_timestamp - self.max_history_seconds
        
        while self._history and self._history[0].timestamp < cutoff_time:
            self._history.popleft()
    
    def get_moving_average(self, window_seconds: int = 10) -> Optional[float]:
        """
        Calculate moving average over specified window.
        
        Args:
            window_seconds: Time window for MA calculation
            
        Returns:
            Moving average price or None if insufficient data
        """
        if not self._history:
            return None
        
        cutoff_time = time.time() - window_seconds
        recent_prices = [
            p.price for p in self._history 
            if p.timestamp >= cutoff_time
        ]
        
        if not recent_prices:
            return None
        
        return statistics.mean(recent_prices)
    
    def get_price_change_pct(self, window_seconds: int = 10) -> Optional[float]:
        """
        Calculate percentage change from moving average.
        
        Args:
            window_seconds: Time window for comparison
            
        Returns:
            Percentage change (e.g., 0.02 for 2% increase) or None
        """
        if self._last_price is None:
            return None
        
        ma = self.get_moving_average(window_seconds)
        if ma is None or ma == 0:
            return None
        
        return (self._last_price - ma) / ma
    
    def get_volatility(self, window_seconds: int = 30) -> Optional[float]:
        """
        Calculate price volatility (standard deviation).
        
        Args:
            window_seconds: Time window for calculation
            
        Returns:
            Standard deviation of prices or None
        """
        if not self._history or len(self._history) < 2:
            return None
        
        cutoff_time = time.time() - window_seconds
        recent_prices = [
            p.price for p in self._history 
            if p.timestamp >= cutoff_time
        ]
        
        if len(recent_prices) < 2:
            return None
        
        return statistics.stdev(recent_prices)
    
    @property
    def last_price(self) -> Optional[float]:
        """Get most recent price."""
        return self._last_price
    
    @property
    def history_size(self) -> int:
        """Get number of data points in history."""
        return len(self._history)
    
    def get_price_history(self, window_seconds: Optional[int] = None) -> List[PricePoint]:
        """
        Get price history within specified window.
        
        Args:
            window_seconds: Time window (None = all history)
            
        Returns:
            List of price points
        """
        if window_seconds is None:
            return list(self._history)
        
        cutoff_time = time.time() - window_seconds
        return [p for p in self._history if p.timestamp >= cutoff_time]
