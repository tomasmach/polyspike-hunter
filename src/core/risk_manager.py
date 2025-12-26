"""
Risk Management for trading bot.
Enforces position sizing, max drawdown, and other safety limits.
"""

from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class RiskManager:
    """
    Enforces risk management rules to prevent excessive losses.
    """
    
    def __init__(
        self,
        min_position_size: float = 1.0,
        max_position_size: float = 5.0,
        max_drawdown: float = 50.0,
        max_open_positions: int = 10,
        min_balance_required: float = 1.0,
    ):
        """
        Initialize risk manager.
        
        Args:
            min_position_size: Minimum position size in USD
            max_position_size: Maximum position size in USD
            max_drawdown: Maximum drawdown before stopping (USD)
            max_open_positions: Maximum number of concurrent positions
            min_balance_required: Minimum balance needed to continue trading
        """
        self.min_position_size = min_position_size
        self.max_position_size = max_position_size
        self.max_drawdown = max_drawdown
        self.max_open_positions = max_open_positions
        self.min_balance_required = min_balance_required
        
        self._emergency_stop = False
        
        logger.info(
            "risk_manager_initialized",
            min_position=min_position_size,
            max_position=max_position_size,
            max_drawdown=max_drawdown,
            max_open_positions=max_open_positions
        )
    
    def validate_position_size(self, size: float) -> tuple[bool, str]:
        """
        Validate if position size is within limits.
        
        Args:
            size: Position size in USD
            
        Returns:
            Tuple of (is_valid, reason)
        """
        if size < self.min_position_size:
            return False, f"position_too_small_min_{self.min_position_size}"
        
        if size > self.max_position_size:
            return False, f"position_too_large_max_{self.max_position_size}"
        
        return True, "valid"
    
    def can_open_position(
        self,
        current_balance: float,
        available_balance: float,
        position_size: float,
        current_positions: int,
        current_drawdown: float,
    ) -> tuple[bool, str]:
        """
        Check if new position can be opened based on all risk criteria.
        
        Args:
            current_balance: Current total balance
            available_balance: Balance available for trading
            position_size: Proposed position size
            current_positions: Number of currently open positions
            current_drawdown: Current drawdown amount
            
        Returns:
            Tuple of (can_open, reason)
        """
        # Check emergency stop
        if self._emergency_stop:
            return False, "emergency_stop_active"
        
        # Check minimum balance
        if current_balance < self.min_balance_required:
            logger.warning(
                "insufficient_balance",
                current=current_balance,
                required=self.min_balance_required
            )
            return False, "insufficient_balance"
        
        # Check max drawdown
        if current_drawdown >= self.max_drawdown:
            logger.error(
                "max_drawdown_exceeded",
                drawdown=current_drawdown,
                max_allowed=self.max_drawdown
            )
            self.trigger_emergency_stop("max_drawdown_exceeded")
            return False, "max_drawdown_exceeded"
        
        # Check position size limits
        valid_size, size_reason = self.validate_position_size(position_size)
        if not valid_size:
            return False, size_reason
        
        # Check available balance
        if position_size > available_balance:
            return False, f"insufficient_available_balance_{available_balance:.2f}"
        
        # Check max concurrent positions
        if current_positions >= self.max_open_positions:
            return False, f"max_positions_reached_{self.max_open_positions}"
        
        return True, "allowed"
    
    def check_drawdown_limit(self, current_drawdown: float) -> bool:
        """
        Check if drawdown limit has been exceeded.
        
        Args:
            current_drawdown: Current drawdown amount
            
        Returns:
            True if limit exceeded (should stop trading)
        """
        if current_drawdown >= self.max_drawdown:
            logger.critical(
                "drawdown_limit_exceeded",
                current=current_drawdown,
                limit=self.max_drawdown
            )
            self.trigger_emergency_stop("drawdown_limit_exceeded")
            return True
        
        # Warning at 80% of max drawdown
        warning_threshold = self.max_drawdown * 0.8
        if current_drawdown >= warning_threshold:
            logger.warning(
                "approaching_drawdown_limit",
                current=current_drawdown,
                limit=self.max_drawdown,
                remaining=self.max_drawdown - current_drawdown
            )
        
        return False
    
    def trigger_emergency_stop(self, reason: str) -> None:
        """
        Trigger emergency stop - prevents all new positions.
        
        Args:
            reason: Reason for emergency stop
        """
        self._emergency_stop = True
        logger.critical(
            "emergency_stop_triggered",
            reason=reason
        )
    
    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop
    
    def reset_emergency_stop(self) -> None:
        """Reset emergency stop (use with caution)."""
        self._emergency_stop = False
        logger.warning("emergency_stop_reset")
    
    def calculate_position_size(
        self,
        available_balance: float,
        desired_size: Optional[float] = None
    ) -> float:
        """
        Calculate appropriate position size within risk limits.
        
        Args:
            available_balance: Balance available for trading
            desired_size: Desired position size (if None, uses max_position_size)
            
        Returns:
            Position size clamped to valid range
        """
        if desired_size is None:
            desired_size = self.max_position_size
        
        # Clamp to limits
        size = max(self.min_position_size, min(desired_size, self.max_position_size))
        
        # Don't exceed available balance
        size = min(size, available_balance)
        
        return size
