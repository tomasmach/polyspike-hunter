"""
PolySpike Hunter - Main Trading Bot
Paper trading mode for Polymarket volatility scalping.
"""

import asyncio
import signal
import sys
from typing import Dict
import structlog

from config.settings import get_settings
from src.core.client import PolymarketClient
from src.core.market_monitor import MarketMonitor, PriceUpdate
from src.core.market_selector import MarketSelector, SelectionStrategy
from src.core.paper_trading import PaperTradingEngine, OrderSide
from src.core.risk_manager import RiskManager
from src.strategy.spike_hunter import SpikeHunterStrategy, SignalType
from src.utils.reporting import SessionReporter, RealTimeStatsTracker

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)


class PolySpikeHunter:
    """
    Main trading bot that integrates all components.
    Monitors markets, detects spikes, and executes paper trades.
    """
    
    def __init__(self):
        """Initialize bot with all components."""
        # Load settings
        logger.info("loading_configuration")
        self.settings = get_settings()
        
        # Initialize Polymarket client
        logger.info("initializing_polymarket_client")
        self.client = PolymarketClient(self.settings.polymarket)
        
        # Initialize paper trading engine
        logger.info(
            "initializing_paper_trading",
            initial_balance=self.settings.paper_trading.initial_balance
        )
        self.paper_engine = PaperTradingEngine(
            initial_balance=self.settings.paper_trading.initial_balance
        )
        
        # Initialize risk manager
        logger.info("initializing_risk_manager")
        self.risk_manager = RiskManager(
            min_position_size=self.settings.paper_trading.min_position_size,
            max_position_size=self.settings.trading.position_size,
            max_drawdown=self.settings.trading.max_drawdown,
            max_open_positions=self.settings.paper_trading.max_open_positions,
        )
        
        # Initialize strategy
        logger.info("initializing_spike_hunter_strategy")
        self.strategy = SpikeHunterStrategy(
            spike_threshold=self.settings.trading.spike_threshold,
            take_profit_pct=self.settings.trading.take_profit_pct,
            stop_loss_pct=self.settings.trading.stop_loss_pct,
        )
        
        # Initialize market selector
        logger.info("initializing_market_selector")
        strategy_map = {
            "volume": SelectionStrategy.VOLUME,
            "random": SelectionStrategy.RANDOM,
            "manual": SelectionStrategy.MANUAL,
        }
        selection_strategy = strategy_map.get(
            self.settings.monitoring.strategy.lower(),
            SelectionStrategy.VOLUME
        )
        
        self.market_selector = MarketSelector(
            strategy=selection_strategy,
            max_markets=self.settings.monitoring.max_monitored_markets,
            min_volume=self.settings.monitoring.min_market_volume,
        )
        
        # Initialize market monitor
        logger.info("initializing_market_monitor")
        self.monitor = MarketMonitor(
            client=self.client,
            selector=self.market_selector,
            poll_interval=self.settings.trading.poll_interval,
            price_history_window=self.settings.monitoring.price_history_window,
            max_concurrent_requests=self.settings.monitoring.max_concurrent_requests,
        )
        
        # Initialize reporting
        logger.info("initializing_session_reporter")
        self.reporter = SessionReporter()
        self.stats_tracker = RealTimeStatsTracker(update_interval=10.0)
        
        # Track current prices for equity calculation
        self._current_prices: Dict[str, float] = {}

        # Running and shutdown flags
        self._running = False
        self._shutdown_complete = False

        logger.info("PolySpikeHunter initialized successfully")
    
    async def start(self) -> None:
        """Start the trading bot."""
        logger.info("Starting PolySpikeHunter...")
        logger.info(
            "configuration",
            paper_trading=self.settings.paper_trading.enabled,
            initial_balance=f"${self.settings.paper_trading.initial_balance:.2f}",
            spike_threshold=f"{self.settings.trading.spike_threshold*100:.1f}%",
            position_size=f"${self.settings.trading.position_size:.2f}",
            monitored_markets=self.settings.monitoring.max_monitored_markets
        )

        # Connect to Polymarket
        logger.info("connecting_to_polymarket")
        await self.client.connect()

        # Register price update callback
        self.monitor.on_price_update(self._handle_price_update)

        # Set running flag
        self._running = True

        # Start monitoring (this will run until cancelled or error)
        logger.info("Bot is now running. Press Ctrl+C to stop.")
        await self.monitor.start()
    
    def _handle_price_update(self, update: PriceUpdate) -> None:
        """
        Handle price update event from market monitor.
        
        Args:
            update: Price update event
        """
        # Track price for equity calculation
        self._current_prices[update.token_id] = update.price
        
        # Record stats
        self.stats_tracker.record_price_update()
        
        # Get price tracker for this token
        tracker = self.monitor.get_tracker(update.token_id)
        if tracker is None:
            return
        
        # Log market snapshot periodically
        if self.stats_tracker.should_print_update():
            self._log_market_snapshot(update, tracker)
            self._print_periodic_update()
        
        # Check if we have position
        has_position = self.paper_engine.has_position(update.token_id)
        position = self.paper_engine.get_position(update.token_id) if has_position else None
        
        # Analyze price update and get signal
        signal = self.strategy.analyze_price_update(
            update=update,
            tracker=tracker,
            has_position=has_position,
            position_entry_price=position.entry_price if position else None
        )
        
        # Execute signal
        if signal.signal_type != SignalType.NONE:
            self.stats_tracker.record_signal()
            self._execute_signal(signal)
    
    def _execute_signal(self, signal) -> None:
        """
        Execute trading signal.
        
        Args:
            signal: Trading signal to execute
        """
        if signal.signal_type == SignalType.ENTRY:
            self._execute_entry(signal)
        elif signal.signal_type == SignalType.EXIT:
            self._execute_exit(signal)
    
    def _execute_entry(self, signal) -> None:
        """Execute entry signal (open position)."""
        # Calculate position size
        available = self.paper_engine.get_available_balance()
        position_size = self.risk_manager.calculate_position_size(
            available_balance=available,
            desired_size=self.settings.trading.position_size
        )
        
        # Check risk constraints
        can_open, reason = self.risk_manager.can_open_position(
            current_balance=self.paper_engine.balance,
            available_balance=available,
            position_size=position_size,
            current_positions=len(self.paper_engine.positions),
            current_drawdown=self.paper_engine.max_drawdown,
        )
        
        if not can_open:
            logger.warning(
                "entry_rejected",
                token_id=signal.token_id[:16] + "...",
                reason=reason
            )
            return
        
        # Execute paper trade
        order = self.paper_engine.create_order(
            token_id=signal.token_id,
            side=OrderSide.BUY,
            size=position_size,
            current_price=signal.price
        )
        
        if order:
            self.stats_tracker.record_trade()
            logger.info(
                "ENTRY EXECUTED",
                token_id=signal.token_id[:16] + "...",
                price=f"{signal.price:.4f}",
                size=f"${position_size:.2f}",
                reason=signal.reason,
                balance=f"${self.paper_engine.balance:.2f}"
            )
    
    def _execute_exit(self, signal) -> None:
        """Execute exit signal (close position)."""
        position = self.paper_engine.get_position(signal.token_id)
        if position is None:
            return
        
        # Execute paper trade
        order = self.paper_engine.create_order(
            token_id=signal.token_id,
            side=OrderSide.SELL,
            size=position.size,
            current_price=signal.price
        )
        
        if order:
            self.stats_tracker.record_trade()
            
            # Log the completed trade
            trade = self.paper_engine.completed_trades[-1]
            self.reporter.log_trade(trade.to_dict())
            
            logger.info(
                "EXIT EXECUTED",
                token_id=signal.token_id[:16] + "...",
                entry_price=f"{position.entry_price:.4f}",
                exit_price=f"{signal.price:.4f}",
                pnl=f"${trade.pnl:+.2f}",
                pnl_pct=f"{trade.pnl_pct*100:+.2f}%",
                reason=signal.reason,
                balance=f"${self.paper_engine.balance:.2f}"
            )
    
    def _log_market_snapshot(self, update: PriceUpdate, tracker) -> None:
        """Log market snapshot to CSV."""
        ma = tracker.get_moving_average(10)
        volatility = tracker.get_volatility(30)
        
        self.reporter.log_market_snapshot(
            token_id=update.token_id,
            price=update.price,
            moving_average=ma,
            price_change_pct=update.price_change_pct,
            volatility=volatility
        )
    
    def _print_periodic_update(self) -> None:
        """Print periodic status update."""
        total_equity = self.paper_engine.get_total_equity(self._current_prices)
        
        self.stats_tracker.print_periodic_update(
            balance=total_equity,
            open_positions=len(self.paper_engine.positions),
            total_pnl=self.paper_engine.total_pnl
        )
    
    async def shutdown(self) -> None:
        """Shutdown bot and cleanup (idempotent)."""
        if self._shutdown_complete:
            return

        logger.info("Shutting down PolySpikeHunter...")

        # Stop monitoring
        await self.monitor.stop()

        # Disconnect client
        self.client.disconnect()

        # Get final statistics
        stats = self.paper_engine.get_statistics()

        # Save and print summary
        self.reporter.save_session_summary(stats)
        self.reporter.print_session_summary(stats)

        self._shutdown_complete = True
        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    bot = PolySpikeHunter()

    # Create task for bot
    bot_task = asyncio.create_task(bot.start())

    # Setup async signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def signal_handler(sig):
        logger.info("interrupt_received", signal=sig)
        logger.info("initiating_graceful_shutdown")
        # Cancel the bot task
        bot_task.cancel()

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    try:
        await bot_task
    except asyncio.CancelledError:
        logger.info("bot_task_cancelled")
        # Ensure shutdown is called
        await bot.shutdown()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
        await bot.shutdown()
    except Exception as e:
        logger.error(
            "fatal_error",
            error=str(e),
            error_type=type(e).__name__
        )
        await bot.shutdown()
        raise


if __name__ == "__main__":
    print("PolySpike Hunter - Paper Trading Mode")
    print("=" * 60)
    print("Starting bot...")
    print()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        sys.exit(1)
