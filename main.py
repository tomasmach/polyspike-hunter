"""
PolySpike Hunter - Main Trading Bot
Paper trading mode for Polymarket volatility scalping.
"""

import asyncio
import signal
import sys
import os
import time
from typing import Dict, Optional
import structlog

from config.settings import get_settings
from src.core.client import PolymarketClient
from src.core.market_monitor import MarketMonitor, PriceUpdate
from src.core.market_selector import MarketSelector, SelectionStrategy
from src.core.paper_trading import PaperTradingEngine, OrderSide
from src.core.risk_manager import RiskManager
from src.strategy.spike_hunter import SpikeHunterStrategy, SignalType
from src.utils.reporting import SessionReporter, RealTimeStatsTracker
from src.utils.market_name_resolver import MarketNameResolver
from src.utils.mqtt_publisher import MQTTPublisher

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)

# Global positions file path (persistent across sessions)
POSITIONS_FILE = "data/positions.json"


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

        # Load existing positions from previous session
        logger.info("loading_positions", file_path=POSITIONS_FILE)
        if self.paper_engine.load_positions(POSITIONS_FILE):
            logger.info(
                "positions_restored",
                count=len(self.paper_engine.positions),
                balance=f"${self.paper_engine.balance:.2f}"
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
            name_resolver=None,  # Will be set after name_resolver is initialized
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

        # Initialize market name resolver
        logger.info("initializing_market_name_resolver")
        self.name_resolver = MarketNameResolver(self.client)
        self.strategy.name_resolver = self.name_resolver  # Inject resolver into strategy

        # Initialize market monitor
        logger.info("initializing_market_monitor")
        self.monitor = MarketMonitor(
            client=self.client,
            selector=self.market_selector,
            poll_interval=self.settings.trading.poll_interval,
            price_history_window=self.settings.monitoring.price_history_window,
            max_concurrent_requests=self.settings.monitoring.max_concurrent_requests,
            name_resolver=self.name_resolver,
        )

        # Initialize MQTT publisher (if enabled)
        self.mqtt_publisher: Optional[MQTTPublisher] = None
        if self.settings.mqtt.enabled:
            logger.info("initializing_mqtt_publisher")
            self.mqtt_publisher = MQTTPublisher(
                host=self.settings.mqtt.host,
                port=self.settings.mqtt.port,
                client_id=self.settings.mqtt.client_id,
            )
        else:
            logger.info("mqtt_disabled", reason="MQTT_ENABLED=false in config")

        # Initialize reporting
        logger.info("initializing_session_reporter")
        self.reporter = SessionReporter()
        self.stats_tracker = RealTimeStatsTracker(update_interval=10.0)
        
        # Track current prices for equity calculation
        self._current_prices: Dict[str, float] = {}

        # Track balance updates
        self._last_balance_value = self.settings.paper_trading.initial_balance

        # Track periodic balance publishes
        self._last_periodic_publish = time.time()

        # Running and shutdown flags
        self._running = False
        self._shutdown_complete = False

        logger.info("PolySpikeHunter initialized successfully")

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to MQTT broker."""
        interval = self.settings.mqtt.heartbeat_interval

        while self._running:
            try:
                await asyncio.sleep(interval)

                if self.mqtt_publisher and self._running:
                    self.mqtt_publisher.publish_bot_status("heartbeat", {
                        "uptime_seconds": int(time.time() - self.reporter.session_start),
                        "balance": self.paper_engine.balance,
                        "open_positions": len(self.paper_engine.positions),
                        "total_trades": self.paper_engine.total_trades,
                    })

            except asyncio.CancelledError:
                logger.debug("heartbeat_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "heartbeat_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
    
    async def _balance_update_loop(self) -> None:
        """
        Send balance updates to MQTT on balance change or periodic interval.
        """
        interval = self.settings.mqtt.balance_update_interval

        while self._running:
            try:
                await asyncio.sleep(5)

                if not self.mqtt_publisher or not self._running:
                    continue

                now = time.time()

                current_balance = self.paper_engine.balance
                total_equity = self.paper_engine.get_total_equity(self._current_prices)
                available = self.paper_engine.get_available_balance()
                locked = sum(pos.size for pos in self.paper_engine.positions.values())
                unrealized_pnl = total_equity - current_balance

                balance_changed = current_balance != self._last_balance_value
                periodic_due = now - self._last_periodic_publish >= interval

                if balance_changed or periodic_due:
                    update_reason = []
                    if balance_changed:
                        update_reason.append("balance_changed")
                        self._last_balance_value = current_balance
                    if periodic_due:
                        update_reason.append("periodic")
                        self._last_periodic_publish = now

                    self.mqtt_publisher.publish_balance_update({
                        "balance": current_balance,
                        "equity": total_equity,
                        "available_balance": available,
                        "locked_in_positions": locked,
                        "unrealized_pnl": unrealized_pnl,
                        "total_pnl": self.paper_engine.total_pnl,
                        "update_reason": ",".join(update_reason),
                    })

                    logger.debug(
                        "balance_update_published",
                        balance=f"${current_balance:.2f}",
                        reason=",".join(update_reason)
                    )

            except asyncio.CancelledError:
                logger.debug("balance_update_loop_cancelled")
                break
            except Exception as e:
                logger.error(
                    "balance_update_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
    
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

        # Connect MQTT if enabled
        if self.mqtt_publisher:
            logger.info("connecting_to_mqtt_broker")
            await self.mqtt_publisher.connect()

        # Connect to Polymarket
        logger.info("connecting_to_polymarket")
        await self.client.connect()

        # Register price update callback
        self.monitor.on_price_update(self._handle_price_update)

        # Initialize market names
        logger.info("fetching_market_names")
        await self.name_resolver.initialize(self.monitor.monitored_markets)

        # Publish bot started event
        if self.mqtt_publisher:
            self.mqtt_publisher.publish_bot_status("started", {
                "session_id": self.reporter.session_id,
                "config": {
                    "initial_balance": self.settings.paper_trading.initial_balance,
                    "spike_threshold": self.settings.trading.spike_threshold,
                    "position_size": self.settings.trading.position_size,
                    "monitored_markets": len(self.monitor.monitored_markets),
                }
            })

        # Set running flag
        self._running = True

        # Start background tasks
        heartbeat_task = None
        balance_task = None
        if self.mqtt_publisher:
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            balance_task = asyncio.create_task(self._balance_update_loop())

        # Start monitoring and wait
        logger.info("Bot is now running. Press Ctrl+C to stop.")
        try:
            await self.monitor.start()
        finally:
            # Cancel background tasks
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            if balance_task:
                balance_task.cancel()
                try:
                    await balance_task
                except asyncio.CancelledError:
                    pass
    
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
        
        # Publish spike detection to MQTT
        if signal.signal_type == SignalType.ENTRY and signal.spike_magnitude:
            if self.mqtt_publisher:
                market_name = self.monitor.get_market_name(signal.token_id)
                self.mqtt_publisher.publish_market_event("spike_detected", {
                    "token_id": signal.token_id,
                    "market_name": market_name,
                    "price": signal.price,
                    "spike_pct": signal.spike_magnitude,
                    "direction": "up" if signal.reason == "spike_up" else "down",
                    "reason": signal.reason,
                })
        
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
            market_name = self.monitor.get_market_name(signal.token_id)
            logger.warning(
                "entry_rejected",
                token_id=signal.token_id,
                market_name=market_name,
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

            # Save positions after opening
            self.paper_engine.save_positions(POSITIONS_FILE)

            if self.mqtt_publisher:
                market_name = self.monitor.get_market_name(signal.token_id)
                self.mqtt_publisher.publish_trading_event("position/opened", {
                    "token_id": signal.token_id,
                    "market_name": market_name,
                    "entry_price": signal.price,
                    "position_size": position_size,
                    "reason": signal.reason,
                    "spike_magnitude": signal.spike_magnitude,
                })

            market_name = self.monitor.get_market_name(signal.token_id)
            logger.info(
                "ENTRY EXECUTED",
                token_id=signal.token_id,
                market_name=market_name,
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

            # Save positions after closing
            self.paper_engine.save_positions(POSITIONS_FILE)

            # Log the completed trade
            trade = self.paper_engine.completed_trades[-1]
            self.reporter.log_trade(trade.to_dict())

            if self.mqtt_publisher:
                market_name = self.monitor.get_market_name(signal.token_id)
                
                # Publish position closed
                self.mqtt_publisher.publish_trading_event("position/closed", {
                    "token_id": signal.token_id,
                    "market_name": market_name,
                    "entry_price": position.entry_price,
                    "exit_price": signal.price,
                    "position_size": position.size,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "duration_seconds": trade.exit_timestamp - trade.entry_timestamp,
                    "exit_reason": signal.reason,
                })
                
                # Publish trade completed
                self.mqtt_publisher.publish_trading_event("trade/completed", {
                    "trade_id": trade.trade_id,
                    "token_id": signal.token_id,
                    "market_name": market_name,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "size": trade.size,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "duration_seconds": trade.exit_timestamp - trade.entry_timestamp,
                    "reason": signal.reason,
                })

            market_name = self.monitor.get_market_name(signal.token_id)
            logger.info(
                "EXIT EXECUTED",
                token_id=signal.token_id,
                market_name=market_name,
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

        # Save positions before shutdown
        self.paper_engine.save_positions(POSITIONS_FILE)
        logger.info("positions_saved_on_shutdown")

        # Get final statistics
        stats = self.paper_engine.get_statistics()

        # Publish bot stopped event
        if self.mqtt_publisher:
            self.mqtt_publisher.publish_bot_status("stopped", {
                "session_id": self.reporter.session_id,
                "final_stats": stats,
            })

            # Disconnect MQTT
            logger.info("disconnecting_from_mqtt_broker")
            await self.mqtt_publisher.disconnect()

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
