# PolySpike Hunter 🏹

A high-frequency trading bot for **Polymarket** designed to capture short-term volatility ("spikes") caused by emotional trading or breaking news. Built with Python and `py-clob-client`.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> ⚠️ **DISCLAIMER:** This software is for **educational purposes only**. Algorithmic trading involves significant risk. The authors are not responsible for any financial losses incurred while using this bot. **Use at your own risk.**

## 🎯 Current Status: Paper Trading Mode

**✅ FULLY IMPLEMENTED - Ready to use!**

The bot currently runs in **Paper Trading Mode**:
- ✅ Real market data from Polymarket API
- ✅ Simulated trades with fake balance ($100 starting)
- ✅ Complete strategy, risk management, and reporting
- ❌ No real money at risk - pure simulation

## ⚡ How It Works

The bot operates on a **Spike Hunter / Mean Reversion** strategy:

1.  **Monitor:** Polls 50 highest-volume Polymarket markets every second
2.  **Detect:** Identifies price spikes (±3% deviation from moving average)
3.  **Enter:** Opens simulated $5 position when spike detected
4.  **Exit:** Closes position at:
    - **Take Profit:** +4% gain
    - **Stop Loss:** -2% loss
5.  **Log:** Records all trades to JSON and market data to CSV

## 🛠️ Features

* **📊 Paper Trading:** Risk-free simulation with fake balance
* **⚡ Low Latency:** Fully asynchronous architecture using `asyncio`
* **🔌 Real Data:** Live market data from Polymarket CLOB API
* **🎯 Smart Strategy:** Spike detection with moving average analysis
* **🛡️ Risk Management:** Position sizing, max drawdown, cooldowns
* **📈 Real-time Reporting:** CSV/JSON logging of trades and market data
* **📡 MQTT Integration:** Real-time events pro Discord bot monitoring
* **🔧 Highly Configurable:** All parameters via `.env` file

## 📡 MQTT Integration

Bot publikuje real-time události přes MQTT pro monitoring a Discord notifikace:

**Události:**
- ✅ Bot status (started/stopped/heartbeat)
- ✅ Spike detection
- ✅ Position opened/closed
- ✅ Trade completed (+ P&L)
- ✅ Balance updates (každých 12h)
- ✅ Session statistics

**MQTT Broker:**
- Localhost (port 1883)
- No authentication
- Topic prefix: `polyspike/`

**Dokumentace:** Viz [docs/MQTT_API.md](docs/MQTT_API.md) pro kompletní API reference.

**Discord Bot:** Samostatný repository (coming soon)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure (Optional)

The bot comes with sensible defaults in `.env.example`. For testing:

```bash
cp .env.example .env
# Edit .env if you want to change settings
```

### 3. Run the Bot

```bash
python run_bot.py
```

Or:

```bash
python main.py
```

### 4. Monitor & Stop

- Watch real-time logs in console
- Press **Ctrl+C** to stop
- Check `data/sessions/TIMESTAMP/` for results

## 📊 What You'll See

```
🏹 PolySpike Hunter - Paper Trading Mode
============================================================
📊 Configuration:
  Initial Balance: $100.0
  Spike Threshold: 3%
  Position Size: $5.0
  Max Markets: 50
============================================================

Starting bot...

2025-12-25T18:10:03Z [info] 🚀 Starting PolySpikeHunter...
2025-12-25T18:10:04Z [info] ✅ Bot is now running. Press Ctrl+C to stop.
2025-12-25T18:10:15Z [info] spike_detected direction=down spike_pct=-3.2%
2025-12-25T18:10:15Z [info] ✅ ENTRY EXECUTED price=0.4800 size=$5.00
2025-12-25T18:10:45Z [info] take_profit_triggered pnl_pct=+4.12%
2025-12-25T18:10:45Z [info] ✅ EXIT EXECUTED pnl=$+0.20 balance=$100.20
...
```

## 📁 Output Files

After each session, find your results in `data/sessions/TIMESTAMP/`:

- **`trades.json`** - All completed trades with entry/exit prices, P&L
- **`markets.csv`** - Market snapshots (price, MA, volatility)
- **`summary.json`** - Session statistics and performance metrics

**MQTT Events:** See `docs/MQTT_API.md` for real-time event streaming via MQTT.

## ⚙️ Configuration

Edit `.env` to customize:

```bash
# Paper Trading
INITIAL_BALANCE=100.0          # Starting fake balance
PAPER_TRADING=true             # Always true for now

# Strategy
SPIKE_THRESHOLD=0.03           # 3% spike to trigger entry
POSITION_SIZE=5.0              # $5 per trade
TAKE_PROFIT_PCT=0.04           # 4% take profit
STOP_LOSS_PCT=0.02             # 2% stop loss

# Monitoring
MAX_MONITORED_MARKETS=50       # Number of markets to watch
MONITOR_STRATEGY=volume        # Use highest volume markets
POLL_INTERVAL=1.0              # Poll every second

# Risk Management
MAX_DRAWDOWN=50.0              # Stop if losses reach $50
MAX_OPEN_POSITIONS=10          # Max concurrent positions

# MQTT Integration
MQTT_ENABLED=true                    # Enable MQTT publishing
MQTT_HOST=localhost                  # MQTT broker host
MQTT_PORT=1883                       # MQTT broker port
MQTT_BALANCE_UPDATE_INTERVAL=43200  # Balance updates (12h)
MQTT_HEARTBEAT_INTERVAL=30          # Heartbeat interval
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Main Bot Loop                     │
│                    (main.py)                        │
└──────────────┬──────────────────────────────────────┘
               │
      ┌────────┴────────┐
      │                 │
┌─────▼──────┐   ┌─────▼─────────┐
│  Market    │   │   Strategy    │
│  Monitor   │──▶│ Spike Hunter  │
└────────────┘   └───────┬───────┘
      │                  │
      │           ┌──────▼────────┐
      │           │ Paper Trading │
      │           │    Engine     │
      │           └──────┬────────┘
      │                  │
┌─────▼──────────────────▼────┐
│      Risk Manager           │
└─────────────┬───────────────┘
              │
      ┌───────▼────────┐
      │   Reporting    │
      │  (CSV/JSON)    │
      └────────────────┘
```

### Core Components:

- **`main.py`** - Main bot orchestrator
- **`src/core/market_monitor.py`** - Async market polling
- **`src/core/paper_trading.py`** - Simulated trading engine
- **`src/strategy/spike_hunter.py`** - Spike detection logic
- **`src/core/risk_manager.py`** - Safety limits and validation
- **`src/utils/reporting.py`** - CSV/JSON logging

## 🧪 Testing

Test individual components:

```bash
# Test API connection
python test_connection.py

# Test market monitoring
python test_monitor.py

# Test MQTT integration
python test_mqtt.py subscribe   # Listen to all MQTT events
python test_mqtt.py publish     # Send test events

# Run full integration test
python -c "from main import PolySpikeHunter; print('✅ All imports OK')"
```

## 📚 Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Detailed setup guide
- **[AGENTS.md](AGENTS.md)** - Development guidelines and architecture
- **[MQTT_API.md](docs/MQTT_API.md)** - MQTT API documentation for Discord bot integration

## 🔮 Roadmap

Future enhancements:

- [ ] Live trading mode (with real API keys and real money)
- [ ] WebSocket support for lower latency
- [ ] More sophisticated strategies (ML-based?)
- [ ] Backtesting framework
- [ ] Web dashboard for monitoring
- [ ] Multiple strategy support

## 📝 License

MIT License - See [LICENSE](LICENSE) for details

## ⚠️ Final Warning

This is **experimental software** for **educational purposes only**. 

- Paper trading mode is **completely safe** (no real money)
- Live trading (when implemented) will involve **real financial risk**
- **Never** trade with money you can't afford to lose
- Cryptocurrency/prediction markets are **highly volatile**
- Past performance does **not** guarantee future results

**Use at your own risk!**
