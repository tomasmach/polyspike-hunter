"""
Reporting and logging utilities for trading sessions.
Handles CSV logging for market data and JSON logging for trades.
"""

import os
import json
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class SessionReporter:
    """
    Handles session reporting, including file-based logging and statistics.
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        output_dir: str = "data/sessions"
    ):
        """
        Initialize session reporter.
        
        Args:
            session_id: Unique session identifier (auto-generated if None)
            output_dir: Directory for output files
        """
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.session_dir = self.output_dir / session_id
        
        # Create directories
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.trades_file = self.session_dir / "trades.json"
        self.markets_file = self.session_dir / "markets.csv"
        self.summary_file = self.session_dir / "summary.json"
        
        # Initialize files
        self._init_trades_file()
        self._init_markets_file()
        
        # Session start time
        self.session_start = time.time()
        
        logger.info(
            "session_reporter_initialized",
            session_id=session_id,
            output_dir=str(self.session_dir)
        )
    
    def _init_trades_file(self) -> None:
        """Initialize trades JSON file."""
        if not self.trades_file.exists():
            with open(self.trades_file, 'w') as f:
                json.dump({"session_id": self.session_id, "trades": []}, f, indent=2)
    
    def _init_markets_file(self) -> None:
        """Initialize markets CSV file."""
        if not self.markets_file.exists():
            with open(self.markets_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "token_id",
                    "price",
                    "moving_average",
                    "price_change_pct",
                    "volatility"
                ])
    
    def log_trade(self, trade_data: Dict[str, Any]) -> None:
        """
        Log a completed trade to JSON file.
        
        Args:
            trade_data: Trade data dictionary
        """
        try:
            # Read existing data
            with open(self.trades_file, 'r') as f:
                data = json.load(f)
            
            # Append new trade
            data["trades"].append(trade_data)
            
            # Write back
            with open(self.trades_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("trade_logged", trade_id=trade_data.get("trade_id"))
            
        except Exception as e:
            logger.error(
                "failed_to_log_trade",
                error=str(e),
                error_type=type(e).__name__
            )
    
    def log_market_snapshot(
        self,
        token_id: str,
        price: float,
        moving_average: Optional[float] = None,
        price_change_pct: Optional[float] = None,
        volatility: Optional[float] = None
    ) -> None:
        """
        Log market data snapshot to CSV.
        
        Args:
            token_id: Token identifier
            price: Current price
            moving_average: Moving average price
            price_change_pct: Price change percentage
            volatility: Price volatility
        """
        try:
            with open(self.markets_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    token_id,
                    f"{price:.6f}" if price else "",
                    f"{moving_average:.6f}" if moving_average else "",
                    f"{price_change_pct:.6f}" if price_change_pct else "",
                    f"{volatility:.6f}" if volatility else ""
                ])
        except Exception as e:
            logger.error(
                "failed_to_log_market_snapshot",
                error=str(e),
                error_type=type(e).__name__
            )
    
    def save_session_summary(self, stats: Dict[str, Any]) -> None:
        """
        Save session summary statistics to JSON.
        
        Args:
            stats: Statistics dictionary
        """
        try:
            summary = {
                "session_id": self.session_id,
                "session_start": self.session_start,
                "session_end": time.time(),
                "duration_seconds": time.time() - self.session_start,
                "statistics": stats
            }
            
            with open(self.summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info("session_summary_saved", file=str(self.summary_file))
            
        except Exception as e:
            logger.error(
                "failed_to_save_summary",
                error=str(e),
                error_type=type(e).__name__
            )
    
    def print_session_summary(self, stats: Dict[str, Any]) -> None:
        """
        Print formatted session summary to console.
        
        Args:
            stats: Statistics dictionary
        """
        duration = time.time() - self.session_start
        duration_str = f"{int(duration // 60)}m {int(duration % 60)}s"
        
        print("\n" + "="*60)
        print(f"Trading Session Summary - {self.session_id}")
        print("="*60)
        print(f"Duration: {duration_str}")
        print("\nFinancial Performance:")
        print(f"  Initial Balance:  ${stats.get('initial_balance', 0):.2f}")
        print(f"  Final Balance:    ${stats.get('current_balance', 0):.2f}")
        print(f"  Total P&L:        ${stats.get('total_pnl', 0):+.2f}")
        print(f"  Total P&L %:      {stats.get('total_pnl_pct', 0)*100:+.2f}%")
        print(f"  Max Drawdown:     ${stats.get('max_drawdown', 0):.2f}")
        
        print("\nTrading Activity:")
        print(f"  Total Trades:     {stats.get('total_trades', 0)}")
        print(f"  Winning Trades:   {stats.get('winning_trades', 0)}")
        print(f"  Losing Trades:    {stats.get('losing_trades', 0)}")
        print(f"  Win Rate:         {stats.get('win_rate', 0)*100:.1f}%")
        
        if stats.get('avg_win', 0) != 0 or stats.get('avg_loss', 0) != 0:
            print(f"  Avg Win:          ${stats.get('avg_win', 0):.2f}")
            print(f"  Avg Loss:         ${stats.get('avg_loss', 0):.2f}")
        
        print("\nOutput Files:")
        print(f"  Trades:  {self.trades_file}")
        print(f"  Markets: {self.markets_file}")
        print(f"  Summary: {self.summary_file}")
        print("="*60 + "\n")


class RealTimeStatsTracker:
    """
    Tracks real-time statistics during trading session.
    """
    
    def __init__(self, update_interval: float = 10.0):
        """
        Initialize stats tracker.
        
        Args:
            update_interval: Seconds between stats updates
        """
        self.update_interval = update_interval
        self._last_update = 0.0
        self._price_updates_count = 0
        self._signals_generated = 0
        self._trades_executed = 0
    
    def record_price_update(self) -> None:
        """Record a price update event."""
        self._price_updates_count += 1
    
    def record_signal(self) -> None:
        """Record a trading signal."""
        self._signals_generated += 1
    
    def record_trade(self) -> None:
        """Record a trade execution."""
        self._trades_executed += 1
    
    def should_print_update(self) -> bool:
        """Check if it's time to print periodic update."""
        current_time = time.time()
        if current_time - self._last_update >= self.update_interval:
            self._last_update = current_time
            return True
        return False
    
    def print_periodic_update(
        self,
        balance: float,
        open_positions: int,
        total_pnl: float
    ) -> None:
        """
        Print periodic status update.
        
        Args:
            balance: Current balance
            open_positions: Number of open positions
            total_pnl: Total P&L
        """
        logger.info(
            "periodic_update",
            balance=f"${balance:.2f}",
            open_positions=open_positions,
            total_pnl=f"${total_pnl:+.2f}",
            price_updates=self._price_updates_count,
            signals=self._signals_generated,
            trades=self._trades_executed
        )
    
    def get_stats(self) -> Dict[str, int]:
        """Get current statistics."""
        return {
            "price_updates": self._price_updates_count,
            "signals_generated": self._signals_generated,
            "trades_executed": self._trades_executed,
        }
