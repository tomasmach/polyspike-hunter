# PolySpike Hunter 🏹

A high-frequency trading bot for **Polymarket** designed to capture short-term volatility ("spikes") caused by emotional trading or breaking news. Built with Python and `py-clob-client`.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> ⚠️ **DISCLAIMER:** This software is for **educational purposes only**. Algorithmic trading involves significant risk. The authors are not responsible for any financial losses incurred while using this bot. **Use at your own risk.**

## ⚡ How It Works

The bot operates on a simple **Mean Reversion / Scalping** strategy:

1.  **Poll:** Monitors specific Polymarket order books via WebSocket/API (async).
2.  **Detect:** Identifies sharp price movements (e.g., >2% drop in seconds).
3.  **Enter:** Buys small positions ($1-$5) at the bottom of the panic spike.
4.  **Exit:** Immediately sets a tight Take Profit (2-4%) or Stop Loss to exit the position as the market stabilizes.

## 🛠️ Features

* **Low Latency:** Fully asynchronous architecture using `asyncio`.
* **Direct Execution:** Uses `py-clob-client` for direct CLOB (Central Limit Order Book) interaction.
* **Safety Rails:** Configurable limits for position size, max drawdown, and stop-losses.
* **Spike Logic:** customizable thresholds for price deviations.
