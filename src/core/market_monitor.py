"""
Market monitoring with async polling.
Continuously polls selected markets and tracks price movements.
"""

import asyncio
from typing import Dict, List, Optional, Callable, TYPE_CHECKING
import structlog
from dataclasses import dataclass
import time

from src.core.client import PolymarketClient
from src.core.market_selector import MarketSelector
from src.utils.price_tracker import PriceTracker
from src.utils.market_name_resolver import MarketNameResolver

if TYPE_CHECKING:
    from src.utils.mqtt_publisher import MQTTPublisher

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
        max_concurrent_requests: int = 10,
        mqtt_publisher: Optional["MQTTPublisher"] = None,
        name_resolver: Optional[MarketNameResolver] = None,
    ):
        """
        Initialize market monitor.

        Args:
            client: Polymarket CLOB client
            selector: Market selection logic
            poll_interval: Seconds between polls
            price_history_window: Seconds of price history to maintain
            max_concurrent_requests: Maximum concurrent API requests (default: 10)
            mqtt_publisher: Optional MQTT publisher for event publishing
            name_resolver: Optional market name resolver for human-readable names
        """
        self.client = client
        self.selector = selector
        self.poll_interval = poll_interval
        self.price_history_window = price_history_window
        self.max_concurrent_requests = max_concurrent_requests
        self.mqtt_publisher = mqtt_publisher
        self.name_resolver = name_resolver

        self._running = False
        self._monitored_tokens: List[str] = []
        self._trackers: Dict[str, PriceTracker] = {}
        self._callbacks: List[Callable[[PriceUpdate], None]] = []
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._callback_failure_counts: Dict[int, int] = {}  # Track callback failures
        self._disabled_callbacks: set = set()  # Circuit breaker for failed callbacks
        self._poll_failure_counts: Dict[str, int] = {}  # Track consecutive poll failures per token
        self._poll_backoff_until: Dict[str, float] = {}  # Exponential backoff timestamps

        logger.info(
            "market_monitor_initialized",
            poll_interval=poll_interval,
            price_history_window=price_history_window,
            max_concurrent_requests=max_concurrent_requests
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

        # Initialize semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        # Select markets to monitor
        await self._initialize_markets()

        # Initialize market names if resolver is provided
        if self.name_resolver:
            await self.name_resolver.initialize(self._monitored_tokens)

        # Start polling loop
        try:
            await self._poll_loop()
        except asyncio.CancelledError:
            logger.info("monitor_cancelled")
            raise  # Re-raise to propagate cancellation
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

        # Cleanup unused trackers to prevent memory leak
        self._cleanup_unused_trackers(self._monitored_tokens)

    def _cleanup_unused_trackers(self, current_tokens: List[str]) -> None:
        """
        Remove trackers for tokens not in current monitoring list.
        Prevents memory leak when market list changes.

        Args:
            current_tokens: List of currently monitored token IDs
        """
        current_tokens_set = set(current_tokens)
        tokens_to_remove = [
            token_id for token_id in self._trackers.keys()
            if token_id not in current_tokens_set
        ]

        for token_id in tokens_to_remove:
            del self._trackers[token_id]
            logger.debug(
                "tracker_removed",
                token_id=token_id,
                reason="Token no longer monitored"
            )

        if tokens_to_remove:
            logger.info(
                "trackers_cleaned_up",
                removed_count=len(tokens_to_remove)
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
        for token_id, result in zip(self._monitored_tokens, results, strict=True):
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
        # Guard against semaphore being None (called before start())
        if self._semaphore is None:
            logger.error(
                "semaphore_not_initialized",
                token_id=token_id,
                message="_poll_market called before start()"
            )
            return

        current_time = time.time()

        # Check exponential backoff - skip if in backoff period
        if token_id in self._poll_backoff_until:
            if current_time < self._poll_backoff_until[token_id]:
                logger.debug(
                    "poll_skipped_backoff",
                    token_id=token_id,
                    backoff_until=self._poll_backoff_until[token_id],
                    remaining_seconds=self._poll_backoff_until[token_id] - current_time
                )
                return
            else:
                # Backoff period expired, remove it
                del self._poll_backoff_until[token_id]

        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            try:
                # Fetch current price
                price = await self.client.get_last_trade_price(token_id)

                if price is None:
                    logger.debug("no_price_data", token_id=token_id)
                    return

                # Validate price range (Polymarket prices are probabilities: 0-1)
                if price < 0 or price > 1.0:
                    logger.warning(
                        "invalid_price_range",
                        token_id=token_id,
                        price=price,
                        message="Price outside valid range [0, 1.0]"
                    )
                    return

                # Update tracker
                tracker = self._trackers.get(token_id)
                if tracker is None:
                    return

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

                # Reset failure count on success
                if token_id in self._poll_failure_counts:
                    self._poll_failure_counts[token_id] = 0

            except Exception as e:
                # Track consecutive failures
                self._poll_failure_counts[token_id] = self._poll_failure_counts.get(token_id, 0) + 1
                failure_count = self._poll_failure_counts[token_id]

                logger.error(
                    "poll_market_failed",
                    token_id=token_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    consecutive_failures=failure_count
                )

                # Exponential backoff: wait 2^failures seconds (max 60s)
                if failure_count >= 3:
                    backoff_seconds = min(2 ** (failure_count - 3), 60)
                    self._poll_backoff_until[token_id] = current_time + backoff_seconds

                    logger.warning(
                        "poll_retry_backoff_activated",
                        token_id=token_id,
                        consecutive_failures=failure_count,
                        backoff_seconds=backoff_seconds
                    )

                # Don't re-raise - allow other markets to continue
                return
    
    def _emit_price_update(self, update: PriceUpdate) -> None:
        """Emit price update to all registered callbacks."""
        for idx, callback in enumerate(self._callbacks):
            # Skip disabled callbacks (circuit breaker)
            if idx in self._disabled_callbacks:
                continue

            try:
                callback(update)
                # Reset failure count on success
                if idx in self._callback_failure_counts:
                    self._callback_failure_counts[idx] = 0
            except Exception as e:
                # Track failure count
                self._callback_failure_counts[idx] = self._callback_failure_counts.get(idx, 0) + 1

                logger.error(
                    "callback_error",
                    token_id=update.token_id,
                    callback_name=callback.__name__ if hasattr(callback, '__name__') else str(callback),
                    error=str(e),
                    error_type=type(e).__name__,
                    failure_count=self._callback_failure_counts[idx]
                )

                # Circuit breaker: disable callback after 3 consecutive failures
                if self._callback_failure_counts[idx] >= 3:
                    self._disabled_callbacks.add(idx)
                    logger.error(
                        "callback_disabled_circuit_breaker",
                        token_id=update.token_id,
                        callback_name=callback.__name__ if hasattr(callback, '__name__') else str(callback),
                        failure_count=self._callback_failure_counts[idx]
                    )
    
    def get_tracker(self, token_id: str) -> Optional[PriceTracker]:
        """Get price tracker for specific token."""
        return self._trackers.get(token_id)
    
    @property
    def monitored_markets(self) -> List[str]:
        """Get list of currently monitored token IDs."""
        return self._monitored_tokens.copy()

    def set_mqtt_publisher(self, publisher: "MQTTPublisher") -> None:
        """Set MQTT publisher for event publishing."""
        self.mqtt_publisher = publisher

    def set_name_resolver(self, resolver: MarketNameResolver) -> None:
        """Set market name resolver."""
        self.name_resolver = resolver

    def get_market_name(self, token_id: str) -> str:
        """
        Get human-readable market name for token ID.

        Args:
            token_id: Token ID to resolve

        Returns:
            Market question string or truncated token ID if resolver not available
        """
        if self.name_resolver:
            return self.name_resolver.get_name_safe(token_id)
        return token_id[:16] + "..." if len(token_id) > 16 else token_id
