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
    ):
        """
        Initialize Spike Hunter strategy.
        
        Args:
            spike_threshold: Minimum price change % to trigger entry
            take_profit_pct: Take profit threshold
            stop_loss_pct: Stop loss threshold
            ma_window_seconds: Moving average calculation window
            cooldown_seconds: Cooldown period after opening position
        """
        self.spike_threshold = spike_threshold
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.ma_window_seconds = ma_window_seconds
        self.cooldown_seconds = cooldown_seconds
        
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
        
        # If no position, check entry conditions
        if not has_position:
            return self._check_entry_conditions(
                update=update,
                tracker=tracker,
                current_time=current_time
            )
        
        return TradingSignal(
            signal_type=SignalType.NONE,
            token_id=update.token_id,
            price=update.price,
            timestamp=update.timestamp,
            reason="no_action"
        )
    
    def _check_entry_conditions(
        self,
        update: PriceUpdate,
        tracker: PriceTracker,
        current_time: float
    ) -> TradingSignal:
        """Check if conditions met for entry signal."""
        
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
            
            logger.info(
                "spike_detected",
                token_id=update.token_id[:16] + "...",
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
        
        # Calculate P&L percentage
        pnl_pct = (update.price - entry_price) / entry_price
        
        # Check take profit
        if pnl_pct >= self.take_profit_pct:
            logger.info(
                "take_profit_triggered",
                token_id=update.token_id[:16] + "...",
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
            logger.info(
                "stop_loss_triggered",
                token_id=update.token_id[:16] + "...",
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
