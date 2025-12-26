"""
Market monitoring with async polling.
Continuously polls selected markets and tracks price movements.
"""

import asyncio
from typing import Dict, List, Optional, Callable
import structlog
from dataclasses import dataclass

from src.core.client import PolymarketClient
from src.core.market_selector import MarketSelector
from src.utils.price_tracker import PriceTracker

logger = structlog.get_logger(__name__)


@dataclass
class PriceUpdate:
    """Price update event."""
    token_id: str
    price: float
    timestamp: float
    price_change_pct: Optional[float] = None


class MarketMonitor:
    """
    Monitors multiple markets via async polling.
    Tracks price history and emits price update events.
    """
    
    def __init__(
        self,
        client: PolymarketClient,
        selector: MarketSelector,
        poll_interval: float = 1.0,
        price_history_window: int = 60,
    ):
        """
        Initialize market monitor.
        
        Args:
            client: Polymarket CLOB client
            selector: Market selection logic
            poll_interval: Seconds between polls
            price_history_window: Seconds of price history to maintain
        """
        self.client = client
        self.selector = selector
        self.poll_interval = poll_interval
        self.price_history_window = price_history_window
        
        self._running = False
        self._monitored_tokens: List[str] = []
        self._trackers: Dict[str, PriceTracker] = {}
        self._callbacks: List[Callable[[PriceUpdate], None]] = []
        
        logger.info(
            "market_monitor_initialized",
            poll_interval=poll_interval,
            price_history_window=price_history_window
        )
    
    def on_price_update(self, callback: Callable[[PriceUpdate], None]) -> None:
        """
        Register callback for price update events.
        
        Args:
            callback: Function to call on price updates
        """
        self._callbacks.append(callback)
    
    async def start(self) -> None:
        """Start monitoring markets."""
        if self._running:
            logger.warning("monitor_already_running")
            return
        
        logger.info("market_monitor_starting")
        self._running = True
        
        # Select markets to monitor
        await self._initialize_markets()
        
        # Start polling loop
        try:
            await self._poll_loop()
        except asyncio.CancelledError:
            logger.info("monitor_cancelled")
        except Exception as e:
            logger.error(
                "monitor_error",
                error=str(e),
                error_type=type(e).__name__
            )
            raise
        finally:
            self._running = False
            logger.info("market_monitor_stopped")
    
    async def stop(self) -> None:
        """Stop monitoring."""
        logger.info("market_monitor_stopping")
        self._running = False
    
    async def _initialize_markets(self) -> None:
        """Fetch and select markets to monitor."""
        logger.info("fetching_available_markets")
        
        # Fetch all markets
        markets_data = await self.client.get_markets()
        all_markets = markets_data.get("data", [])
        
        # Select markets based on strategy
        self._monitored_tokens = self.selector.select_markets(all_markets)
        
        # Initialize price trackers
        self._trackers = {
            token_id: PriceTracker(token_id, self.price_history_window)
            for token_id in self._monitored_tokens
        }
        
        if len(self._monitored_tokens) == 0:
            logger.error(
                "no_markets_selected",
                total_available=len(all_markets),
                strategy=self.selector.strategy.value
            )
            logger.error("No markets to monitor! Check your configuration.")
        else:
            logger.info(
                "markets_initialized",
                monitored_count=len(self._monitored_tokens)
            )
    
    async def _poll_loop(self) -> None:
        """Main polling loop."""
        if len(self._monitored_tokens) == 0:
            logger.warning("no_markets_to_monitor_exiting")
            return
        
        while self._running:
            loop_start = asyncio.get_event_loop().time()
            
            # Poll all markets in parallel
            await self._poll_all_markets()
            
            # Calculate sleep time to maintain interval
            elapsed = asyncio.get_event_loop().time() - loop_start
            sleep_time = max(0, self.poll_interval - elapsed)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    async def _poll_all_markets(self) -> None:
        """Poll all monitored markets in parallel."""
        tasks = [
            self._poll_market(token_id)
            for token_id in self._monitored_tokens
        ]
        
        # Gather with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log errors
        for token_id, result in zip(self._monitored_tokens, results):
            if isinstance(result, Exception):
                logger.error(
                    "poll_market_error",
                    token_id=token_id,
                    error=str(result),
                    error_type=type(result).__name__
                )
    
    async def _poll_market(self, token_id: str) -> None:
        """
        Poll single market and update tracker.
        
        Args:
            token_id: Token ID to poll
        """
        try:
            # Fetch current price
            price = await self.client.get_last_trade_price(token_id)
            
            if price is None:
                logger.debug("no_price_data", token_id=token_id)
                return
            
            # Update tracker
            tracker = self._trackers.get(token_id)
            if tracker is None:
                return
            
            import time
            timestamp = time.time()
            tracker.add_price(price, timestamp)
            
            # Calculate price change
            price_change_pct = tracker.get_price_change_pct(window_seconds=10)
            
            # Emit price update event
            update = PriceUpdate(
                token_id=token_id,
                price=price,
                timestamp=timestamp,
                price_change_pct=price_change_pct
            )
            
            self._emit_price_update(update)
            
        except Exception as e:
            logger.error(
                "poll_market_failed",
                token_id=token_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
    
    def _emit_price_update(self, update: PriceUpdate) -> None:
        """Emit price update to all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(update)
            except Exception as e:
                logger.error(
                    "callback_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
    
    def get_tracker(self, token_id: str) -> Optional[PriceTracker]:
        """Get price tracker for specific token."""
        return self._trackers.get(token_id)
    
    @property
    def monitored_markets(self) -> List[str]:
        """Get list of currently monitored token IDs."""
        return self._monitored_tokens.copy()
