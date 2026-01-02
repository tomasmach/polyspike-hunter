"""
Spike Hunter Trading Strategy.
Detects price spikes and generates entry/exit signals for mean reversion trading.
"""

import time
from typing import Optional, Dict, Set
from dataclasses import dataclass
from enum import Enum
import structlog

from src.core.market_monitor import PriceUpdate
from src.utils.price_tracker import PriceTracker
from src.utils.market_name_resolver import MarketNameResolver

logger = structlog.get_logger(__name__)


class SignalType(Enum):
    """Trading signal types."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    NONE = "NONE"


@dataclass
class TradingSignal:
    """Represents a trading signal."""
    signal_type: SignalType
    token_id: str
    price: float
    timestamp: float
    reason: str
    spike_magnitude: Optional[float] = None  # Percentage change that triggered signal


class SpikeHunterStrategy:
    """
    Spike Hunter strategy for mean reversion / volatility scalping.
    
    Strategy Logic:
    1. Monitor price changes vs moving average
    2. Entry: When spike > threshold (panic selling/buying)
    3. Exit: Take profit or stop loss based on position P&L
    """
    
    def __init__(
        self,
        spike_threshold: float = 0.03,  # 3% spike to trigger entry
        take_profit_pct: float = 0.04,  # 4% take profit
        stop_loss_pct: float = 0.02,    # 2% stop loss
        ma_window_seconds: int = 10,    # Moving average window
        cooldown_seconds: int = 30,     # Cooldown after entering position
        name_resolver: Optional[MarketNameResolver] = None,
    ):
        """
        Initialize Spike Hunter strategy.

        Args:
            spike_threshold: Minimum price change % to trigger entry
            take_profit_pct: Take profit threshold
            stop_loss_pct: Stop loss threshold
            ma_window_seconds: Moving average calculation window
            cooldown_seconds: Cooldown period after opening position
            name_resolver: Optional market name resolver for human-readable names
        """
        self.spike_threshold = spike_threshold
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.ma_window_seconds = ma_window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.name_resolver = name_resolver

        # Track recent entries to prevent spam
        self._recent_entries: Dict[str, float] = {}  # token_id -> timestamp

        logger.info(
            "spike_hunter_initialized",
            spike_threshold=spike_threshold,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            ma_window=ma_window_seconds,
            cooldown=cooldown_seconds
        )

    def _get_market_name(self, token_id: str) -> str:
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

    def _validate_price(self, price: Optional[float]) -> bool:
        """
        Validate that a price value is valid for Polymarket.

        Args:
            price: Price value to validate

        Returns:
            True if price is valid, False otherwise
        """
        if price is None:
            return False
        if price < 0:
            return False
        if price > 1.0:  # Max valid price in Polymarket
            return False
        return True

    def analyze_price_update(
        self,
        update: PriceUpdate,
        tracker: PriceTracker,
        has_position: bool,
        position_entry_price: Optional[float] = None
    ) -> TradingSignal:
        """
        Analyze price update and generate trading signal.
        
        Args:
            update: Price update event
            tracker: Price tracker for this token
            has_position: Whether we currently have position in this token
            position_entry_price: Entry price if position exists
            
        Returns:
            TradingSignal (ENTRY, EXIT, or NONE)
        """
        current_time = time.time()
        
        # If we have position, check exit conditions
        if has_position and position_entry_price is not None:
            return self._check_exit_conditions(
                update=update,
                entry_price=position_entry_price
            )
        
        # No position, check entry conditions
        return self._check_entry_conditions(
            update=update,
            tracker=tracker,
            current_time=current_time
            )
    
    def _check_entry_conditions(
        self,
        update: PriceUpdate,
        tracker: PriceTracker,
        current_time: float
    ) -> TradingSignal:
        """Check if conditions met for entry signal."""

        # Validate price before processing
        if not self._validate_price(update.price):
            market_name = self._get_market_name(update.token_id)
            logger.warning(
                "invalid_price_in_entry_check",
                token_id=update.token_id,
                market_name=market_name,
                price=update.price
            )
            return TradingSignal(
                signal_type=SignalType.NONE,
                token_id=update.token_id,
                price=update.price if update.price is not None else 0.0,
                timestamp=update.timestamp,
                reason="invalid_price"
            )

        # Check cooldown
        last_entry = self._recent_entries.get(update.token_id)
        if last_entry is not None:
            time_since_entry = current_time - last_entry
            if time_since_entry < self.cooldown_seconds:
                return TradingSignal(
                    signal_type=SignalType.NONE,
                    token_id=update.token_id,
                    price=update.price,
                    timestamp=update.timestamp,
                    reason=f"cooldown_{int(self.cooldown_seconds - time_since_entry)}s"
                )
        
        # Calculate price change vs MA
        ma = tracker.get_moving_average(self.ma_window_seconds)
        if ma is None or ma == 0:
            market_name = self._get_market_name(update.token_id)
            logger.debug(
                "insufficient_data_for_ma",
                token_id=update.token_id,
                market_name=market_name,
                ma_window=self.ma_window_seconds,
                reason="Not enough price history to calculate moving average"
            )
            return TradingSignal(
                signal_type=SignalType.NONE,
                token_id=update.token_id,
                price=update.price,
                timestamp=update.timestamp,
                reason="insufficient_data"
            )
        
        price_change_pct = (update.price - ma) / ma
        
        # Check for spike (both up and down)
        spike_magnitude = abs(price_change_pct)
        
        if spike_magnitude >= self.spike_threshold:
            # Record entry time for cooldown
            self._recent_entries[update.token_id] = current_time

            direction = "up" if price_change_pct > 0 else "down"
            market_name = self._get_market_name(update.token_id)

            logger.info(
                "spike_detected",
                token_id=update.token_id,
                market_name=market_name,
                price=update.price,
                ma=ma,
                spike_pct=f"{price_change_pct*100:+.2f}%",
                direction=direction
            )
            
            return TradingSignal(
                signal_type=SignalType.ENTRY,
                token_id=update.token_id,
                price=update.price,
                timestamp=update.timestamp,
                reason=f"spike_{direction}",
                spike_magnitude=spike_magnitude
            )
        
        return TradingSignal(
            signal_type=SignalType.NONE,
            token_id=update.token_id,
            price=update.price,
            timestamp=update.timestamp,
            reason="no_spike"
        )
    
    def _check_exit_conditions(
        self,
        update: PriceUpdate,
        entry_price: float
    ) -> TradingSignal:
        """Check if conditions met for exit signal."""

        # Validate current price
        if not self._validate_price(update.price):
            market_name = self._get_market_name(update.token_id)
            logger.error(
                "invalid_current_price_in_exit_check",
                token_id=update.token_id,
                market_name=market_name,
                current_price=update.price,
                entry_price=entry_price
            )
            return TradingSignal(
                signal_type=SignalType.NONE,
                token_id=update.token_id,
                price=update.price if update.price is not None else 0.0,
                timestamp=update.timestamp,
                reason="invalid_price"
            )

        # Validate entry price to prevent division by zero
        if entry_price is None or entry_price == 0:
            market_name = self._get_market_name(update.token_id)
            logger.error(
                "invalid_entry_price_in_exit_check",
                token_id=update.token_id,
                market_name=market_name,
                entry_price=entry_price,
                current_price=update.price,
                reason="Entry price is invalid (None or 0), cannot calculate P&L"
            )
            return TradingSignal(
                signal_type=SignalType.NONE,
                token_id=update.token_id,
                price=update.price,
                timestamp=update.timestamp,
                reason="invalid_entry_price"
            )

        # Calculate P&L percentage
        pnl_pct = (update.price - entry_price) / entry_price
        
        # Check take profit
        if pnl_pct >= self.take_profit_pct:
            market_name = self._get_market_name(update.token_id)
            logger.info(
                "take_profit_triggered",
                token_id=update.token_id,
                market_name=market_name,
                entry_price=entry_price,
                current_price=update.price,
                pnl_pct=f"{pnl_pct*100:+.2f}%"
            )
            return TradingSignal(
                signal_type=SignalType.EXIT,
                token_id=update.token_id,
                price=update.price,
                timestamp=update.timestamp,
                reason="take_profit",
                spike_magnitude=pnl_pct
            )
        
        # Check stop loss
        if pnl_pct <= -self.stop_loss_pct:
            market_name = self._get_market_name(update.token_id)
            logger.info(
                "stop_loss_triggered",
                token_id=update.token_id,
                market_name=market_name,
                entry_price=entry_price,
                current_price=update.price,
                pnl_pct=f"{pnl_pct*100:+.2f}%"
            )
            return TradingSignal(
                signal_type=SignalType.EXIT,
                token_id=update.token_id,
                price=update.price,
                timestamp=update.timestamp,
                reason="stop_loss",
                spike_magnitude=pnl_pct
            )
        
        return TradingSignal(
            signal_type=SignalType.NONE,
            token_id=update.token_id,
            price=update.price,
            timestamp=update.timestamp,
            reason="holding"
        )
    
    def reset_cooldown(self, token_id: str) -> None:
        """Reset cooldown for specific token."""
        if token_id in self._recent_entries:
            del self._recent_entries[token_id]
    
    def clear_all_cooldowns(self) -> None:
        """Clear all cooldowns."""
        self._recent_entries.clear()
