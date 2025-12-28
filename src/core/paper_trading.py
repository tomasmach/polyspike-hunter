"""
Paper Trading Engine for simulated trading.
Maintains fake balance and simulates order fills based on real market prices.
"""

import time
import uuid
import json
import os
import tempfile
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, field, asdict
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class OrderSide(Enum):
    """Order side enum."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status enum."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class PaperOrder:
    """Represents a simulated order."""
    order_id: str
    token_id: str
    side: OrderSide
    size: float  # Amount in USD
    price: Optional[float] = None  # Entry price (filled price)
    status: OrderStatus = OrderStatus.PENDING
    timestamp: float = field(default_factory=time.time)
    filled_timestamp: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "order_id": self.order_id,
            "token_id": self.token_id,
            "side": self.side.value,
            "size": self.size,
            "price": self.price,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "filled_timestamp": self.filled_timestamp,
        }


@dataclass
class Position:
    """Represents an open position."""
    token_id: str
    entry_price: float
    size: float  # Position size in USD
    entry_timestamp: float
    order_id: str
    
    def get_pnl(self, current_price: float) -> float:
        """Calculate current P&L."""
        if self.entry_price == 0:
            return 0.0
        return (current_price - self.entry_price) * (self.size / self.entry_price)
    
    def get_pnl_pct(self, current_price: float) -> float:
        """Calculate P&L percentage."""
        if self.entry_price == 0:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "token_id": self.token_id,
            "entry_price": self.entry_price,
            "size": self.size,
            "entry_timestamp": self.entry_timestamp,
            "order_id": self.order_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        """Create Position from dictionary."""
        return cls(
            token_id=data["token_id"],
            entry_price=data["entry_price"],
            size=data["size"],
            entry_timestamp=data["entry_timestamp"],
            order_id=data["order_id"],
        )


@dataclass
class Trade:
    """Represents a completed trade (entry + exit)."""
    trade_id: str
    token_id: str
    entry_price: float
    exit_price: float
    size: float
    entry_timestamp: float
    exit_timestamp: float
    pnl: float
    pnl_pct: float
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "trade_id": self.trade_id,
            "token_id": self.token_id,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size": self.size,
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "duration_seconds": self.exit_timestamp - self.entry_timestamp,
        }


class PaperTradingEngine:
    """
    Paper trading engine that simulates order execution.
    Maintains fake balance and tracks positions without real money.
    
    Balance Accounting Model:
    - self.balance: Total cash (includes locked capital in open positions)
    - Available balance: self.balance - sum(position.size) for all open positions
    - On position open: Capital is "locked" (no change to balance)
    - On position close: Only P&L is added/subtracted to balance (capital unlocks)
    """
    
    def __init__(self, initial_balance: float = 100.0):
        """
        Initialize paper trading engine.
        
        Args:
            initial_balance: Starting balance in USD
        """
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, PaperOrder] = {}
        self.completed_trades: List[Trade] = []
        
        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.peak_balance = initial_balance
        self.max_drawdown = 0.0
        
        logger.info(
            "paper_trading_initialized",
            initial_balance=initial_balance
        )
    
    def get_available_balance(self) -> float:
        """
        Get balance available for trading (excluding locked in positions).
        
        Balance Model: self.balance represents total cash, positions lock capital.
        - When opening: position size is locked (subtracted from available balance)
        - When closing: only P&L is added/subtracted to balance (position unlocks)
        """
        locked = sum(pos.size for pos in self.positions.values())
        return self.balance - locked
    
    def get_total_equity(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total equity (balance + unrealized P&L).
        
        Args:
            current_prices: Dict mapping token_id to current price
            
        Returns:
            Total equity in USD
        """
        unrealized_pnl = 0.0
        for pos in self.positions.values():
            current_price = current_prices.get(pos.token_id)
            if current_price is not None:
                unrealized_pnl += pos.get_pnl(current_price)
        
        return self.balance + unrealized_pnl
    
    def create_order(
        self,
        token_id: str,
        side: OrderSide,
        size: float,
        current_price: float
    ) -> Optional[PaperOrder]:
        """
        Create and immediately fill a simulated order.
        
        Args:
            token_id: Token to trade
            side: BUY or SELL
            size: Order size in USD
            current_price: Current market price for fill simulation
            
        Returns:
            PaperOrder if successful, None if rejected
        """
        # Validate balance for BUY orders
        if side == OrderSide.BUY:
            available = self.get_available_balance()
            if size > available:
                logger.warning(
                    "order_rejected_insufficient_balance",
                    token_id=token_id,
                    required=size,
                    available=available
                )
                order = PaperOrder(
                    order_id=str(uuid.uuid4()),
                    token_id=token_id,
                    side=side,
                    size=size,
                    status=OrderStatus.REJECTED
                )
                self.orders[order.order_id] = order
                return None
        
        # Validate position exists for SELL orders
        if side == OrderSide.SELL:
            if token_id not in self.positions:
                logger.warning(
                    "order_rejected_no_position",
                    token_id=token_id
                )
                order = PaperOrder(
                    order_id=str(uuid.uuid4()),
                    token_id=token_id,
                    side=side,
                    size=size,
                    status=OrderStatus.REJECTED
                )
                self.orders[order.order_id] = order
                return None
        
        # Create and fill order
        order = PaperOrder(
            order_id=str(uuid.uuid4()),
            token_id=token_id,
            side=side,
            size=size,
            price=current_price,
            status=OrderStatus.FILLED,
            filled_timestamp=time.time()
        )
        
        self.orders[order.order_id] = order
        
        # Update positions
        if side == OrderSide.BUY:
            self._open_position(order)
        else:
            self._close_position(order)
        
        logger.info(
            "paper_order_filled",
            order_id=order.order_id,
            token_id=token_id,
            side=side.value,
            size=size,
            price=current_price,
            balance=self.balance
        )
        
        return order
    
    def _open_position(self, order: PaperOrder) -> None:
        """Open a new position from BUY order."""
        if order.price is None or order.filled_timestamp is None:
            logger.error("cannot_open_position_missing_data", order_id=order.order_id)
            return
        
        position = Position(
            token_id=order.token_id,
            entry_price=order.price,
            size=order.size,
            entry_timestamp=order.filled_timestamp,
            order_id=order.order_id
        )
        
        self.positions[order.token_id] = position
        
        logger.info(
            "position_opened",
            token_id=order.token_id,
            entry_price=order.price,
            size=order.size,
            open_positions=len(self.positions)
        )
    
    def _close_position(self, order: PaperOrder) -> None:
        """Close position from SELL order."""
        position = self.positions.get(order.token_id)
        if position is None:
            return
        
        if order.price is None or order.filled_timestamp is None:
            logger.error("cannot_close_position_missing_data", order_id=order.order_id)
            return
        
        # Type narrowing - we know these are not None after the check
        exit_price: float = order.price
        exit_timestamp: float = order.filled_timestamp
        
        # Calculate P&L
        pnl = position.get_pnl(exit_price)
        pnl_pct = position.get_pnl_pct(exit_price)
        
        # Update balance - only add/subtract P&L (position size was never subtracted from balance)
        self.balance += pnl
        
        # Update statistics
        self.total_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Track drawdown
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance
        drawdown = self.peak_balance - self.balance
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        
        # Create trade record
        trade = Trade(
            trade_id=str(uuid.uuid4()),
            token_id=order.token_id,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.size,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_timestamp,
            pnl=pnl,
            pnl_pct=pnl_pct
        )
        self.completed_trades.append(trade)
        
        # Remove position
        del self.positions[order.token_id]
        
        logger.info(
            "position_closed",
            token_id=order.token_id,
            entry_price=position.entry_price,
            exit_price=exit_price,
            pnl=pnl,
            pnl_pct=f"{pnl_pct*100:.2f}%",
            balance=self.balance,
            open_positions=len(self.positions)
        )
    
    def has_position(self, token_id: str) -> bool:
        """Check if position exists for token."""
        return token_id in self.positions
    
    def get_position(self, token_id: str) -> Optional[Position]:
        """Get position for token."""
        return self.positions.get(token_id)
    
    def get_statistics(self) -> Dict:
        """Get current trading statistics."""
        win_rate = 0.0
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades
        
        avg_win = 0.0
        avg_loss = 0.0
        
        wins = [t.pnl for t in self.completed_trades if t.pnl > 0]
        losses = [t.pnl for t in self.completed_trades if t.pnl <= 0]
        
        if wins:
            avg_win = sum(wins) / len(wins)
        if losses:
            avg_loss = sum(losses) / len(losses)
        
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.balance,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": (self.balance - self.initial_balance) / self.initial_balance,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "open_positions": len(self.positions),
            "max_drawdown": self.max_drawdown,
            "peak_balance": self.peak_balance,
        }
    
    def reset(self) -> None:
        """Reset engine to initial state."""
        self.balance = self.initial_balance
        self.positions.clear()
        self.orders.clear()
        self.completed_trades.clear()
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.peak_balance = self.initial_balance
        self.max_drawdown = 0.0

        logger.info("paper_trading_engine_reset")

    def save_positions(self, file_path: str) -> None:
        """
        Save open positions to JSON file atomically.

        Uses temp file + rename pattern to ensure file is never left in inconsistent state.
        This prevents data corruption if process crashes during write.

        Args:
            file_path: Path to save positions JSON file
        """
        try:
            # Prepare data
            data = {
                "positions": [pos.to_dict() for pos in self.positions.values()],
                "balance": self.balance,
                "timestamp": time.time(),
            }

            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Atomic write: write to temp file then rename
            fd, temp_path = tempfile.mkstemp(
                dir=os.path.dirname(file_path),
                prefix='.positions_',
                suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w') as f:
                    json.dump(data, f, indent=2)
                # Atomic operation on POSIX systems
                os.replace(temp_path, file_path)
            except:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise

            logger.info(
                "positions_saved",
                file_path=file_path,
                position_count=len(self.positions)
            )

        except Exception as e:
            logger.error(
                "failed_to_save_positions",
                error=str(e),
                error_type=type(e).__name__,
                file_path=file_path
            )

    def load_positions(self, file_path: str) -> bool:
        """
        Load positions from JSON file and restore state.

        Args:
            file_path: Path to positions JSON file

        Returns:
            True if positions were loaded successfully, False otherwise
        """
        if not os.path.exists(file_path):
            logger.info("no_positions_file_found", file_path=file_path)
            return False

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Restore positions
            loaded_positions = []
            for pos_data in data.get("positions", []):
                position = Position.from_dict(pos_data)
                self.positions[position.token_id] = position
                loaded_positions.append(position.token_id)

            # Restore balance if saved
            if "balance" in data:
                self.balance = data["balance"]

            logger.info(
                "positions_loaded",
                file_path=file_path,
                position_count=len(loaded_positions),
                positions=loaded_positions,
                balance=self.balance
            )

            return True

        except Exception as e:
            logger.error(
                "failed_to_load_positions",
                error=str(e),
                error_type=type(e).__name__,
                file_path=file_path
            )
            return False
