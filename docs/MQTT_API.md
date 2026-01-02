# PolySpike Hunter - MQTT API Documentation

**Verze:** 1.0
**Datum:** 2026-01-02
**Pro:** Discord Bot Integration

---

## 📡 Přehled

PolySpike Hunter trading bot publikuje real-time události přes MQTT pro monitoring a notifikace.

### MQTT Broker

- **Host:** `localhost` (běží na stejném Raspberry Pi jako bot)
- **Port:** 1883
- **Autentizace:** NE (lokální síť, bez hesla)
- **Protocol:** MQTT v3.1.1
- **Topic Prefix:** `polyspike/`
- **Formát zpráv:** JSON

---

## 📋 Topic Struktura

```
polyspike/
├── status/
│   ├── bot/started              # Bot se spustil
│   ├── bot/stopped              # Bot se zastavil
│   ├── bot/heartbeat            # Heartbeat (každých 30s)
│   └── bot/error                # Kritická chyba
│
├── market/
│   └── spike_detected           # Detekce price spiků
│
├── trading/
│   ├── position/opened          # Pozice otevřena
│   ├── position/closed          # Pozice uzavřena
│   └── trade/completed          # Trade ukončen (+ P&L)
│
├── balance/
│   └── update                   # Balance update (12h nebo změna)
│
└── stats/
    ├── periodic                 # Periodické stats (10s)
    └── session                  # Session summary (při ukončení)
```

---

## 🔒 QoS Levels

| Topic Pattern | QoS | Retain | Popis |
|--------------|-----|--------|-------|
| `status/bot/*` | 1 | heartbeat=YES | Kritické status zprávy |
| `market/*` | 0 | NO | Market events (high-frequency) |
| `trading/*` | 1 | NO | Trading events (MUST NOT miss) |
| `balance/*` | 1 | YES | Balance updates |
| `stats/*` | 1 | session=YES | Statistics |

### QoS Vysvětlení

- **QoS 0:** At most once (může se ztratit)
- **QoS 1:** At least once (garantováno doručení, možné duplikáty)

### Retained Messages

Subscriber dostane poslední zprávu i když se připojí po publish:

- `status/bot/heartbeat` - poslední stav bota
- `balance/update` - poslední balance
- `stats/session` - poslední session summary

---

## 📨 Message Payloads

### 1. Bot Status Events

#### `polyspike/status/bot/started`

**Kdy:** Bot se spustil
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833600.123,
  "session_id": "20260102_180000",
  "config": {
    "initial_balance": 100.0,
    "spike_threshold": 0.03,
    "position_size": 5.0,
    "monitored_markets": 50
  }
}
```

**Fields:**

- `timestamp` (float): Unix timestamp
- `session_id` (string): Unikátní ID session
- `config.initial_balance` (float): Starting balance v USD
- `config.spike_threshold` (float): Spike detection threshold (0.03 = 3%)
- `config.position_size` (float): Position size v USD
- `config.monitored_markets` (int): Počet monitorovaných trhů

---

#### `polyspike/status/bot/heartbeat`

**Kdy:** Každých 30 sekund
**QoS:** 0
**Retain:** YES

```json
{
  "timestamp": 1735833630.456,
  "uptime_seconds": 3600,
  "balance": 105.23,
  "open_positions": 2,
  "total_trades": 15
}
```

**Fields:**

- `uptime_seconds` (int): Uptime v sekundách
- `balance` (float): Aktuální balance
- `open_positions` (int): Počet otevřených pozic
- `total_trades` (int): Celkový počet tradů

**Použití:** Health check (pokud heartbeat chybí >60s, bot je pravděpodobně down)

---

#### `polyspike/status/bot/stopped`

**Kdy:** Bot se zastavil (graceful shutdown)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735837200.789,
  "session_id": "20260102_180000",
  "final_stats": {
    "total_pnl": 5.23,
    "total_trades": 25,
    "win_rate": 0.72
  }
}
```

---

#### `polyspike/status/bot/error`

**Kdy:** Kritická chyba (connection loss, crash)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833650.789,
  "error_type": "ConnectionError",
  "error_message": "Failed to connect to Polymarket API",
  "severity": "critical"
}
```

**Fields:**

- `error_type` (string): Python exception type
- `error_message` (string): Error popis
- `severity` (string): "critical" | "error" | "warning"

---

### 2. Market Events

#### `polyspike/market/spike_detected`

**Kdy:** Detekován price spike (±3%+)
**QoS:** 0
**Retain:** NO

```json
{
  "timestamp": 1735833700.123,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "price": 0.4800,
  "spike_pct": -0.032,
  "direction": "down",
  "reason": "spike_down"
}
```

**Fields:**

- `token_id` (string): Polymarket token ID (hash)
- `market_name` (string): Čitelný název trhu
- `price` (float): Aktuální cena (0.0 - 1.0)
- `spike_pct` (float): Velikost spiků (absolute, -0.032 = -3.2%)
- `direction` (string): "up" | "down"
- `reason` (string): "spike_up" | "spike_down"

**Poznámka:** Spike detection NEznamená že bot otevřel pozici (může být rejected risk managerem)

---

### 3. Trading Events

#### `polyspike/trading/position/opened`

**Kdy:** Pozice otevřena (BUY executed)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833715.789,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "position_size": 5.0,
  "reason": "spike_down",
  "spike_magnitude": 0.032
}
```

**Fields:**

- `entry_price` (float): Cena vstupu
- `position_size` (float): Velikost pozice v USD
- `spike_magnitude` (float): Velikost spiků co triggered entry

---

#### `polyspike/trading/position/closed`

**Kdy:** Pozice uzavřena (SELL executed)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833745.012,
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "exit_price": 0.4992,
  "position_size": 5.0,
  "pnl": 0.20,
  "pnl_pct": 0.04,
  "duration_seconds": 30,
  "exit_reason": "take_profit"
}
```

**Fields:**

- `exit_price` (float): Cena výstupu
- `pnl` (float): Profit & Loss v USD
- `pnl_pct` (float): P&L percentage (0.04 = 4%)
- `duration_seconds` (int): Doba držení pozice
- `exit_reason` (string): "take_profit" | "stop_loss"

---

#### `polyspike/trading/trade/completed`

**Kdy:** Trade kompletně ukončen (summary)
**QoS:** 1
**Retain:** NO

```json
{
  "timestamp": 1735833745.012,
  "trade_id": "a1b2c3d4-5678-...",
  "token_id": "0x1234abcd5678...",
  "market_name": "Will Trump win 2024?",
  "entry_price": 0.4800,
  "exit_price": 0.4992,
  "size": 5.0,
  "pnl": 0.20,
  "pnl_pct": 0.04,
  "duration_seconds": 30,
  "reason": "take_profit"
}
```

**Fields:**

- `trade_id` (string): Unikátní trade ID (UUID)
- Ostatní fields stejné jako `position/closed`

**Rozdíl `position/closed` vs `trade/completed`:**

- `position/closed` - okamžitý event po SELL
- `trade/completed` - summary s `trade_id` (pro logging/analytics)

---

### 4. Balance Updates

#### `polyspike/balance/update`

**Kdy:**

- Každých 12 hodin (43200s)
- Když balance změní o >5%
- Po každém completed trade

**QoS:** 1
**Retain:** YES

```json
{
  "timestamp": 1735833750.345,
  "balance": 100.20,
  "equity": 100.45,
  "available_balance": 90.20,
  "locked_in_positions": 10.0,
  "unrealized_pnl": 0.25,
  "total_pnl": 0.20,
  "update_reason": "periodic"
}
```

**Fields:**

- `balance` (float): Cash balance
- `equity` (float): Balance + unrealized P&L
- `available_balance` (float): Balance - locked capital
- `locked_in_positions` (float): Capital v otevřených pozicích
- `unrealized_pnl` (float): Unrealized profit/loss
- `total_pnl` (float): Total realized P&L (od začátku)
- `update_reason` (string): "periodic" | "significant_change" | "trade"

---

### 5. Statistics

#### `polyspike/stats/periodic`

**Kdy:** Každých 10 sekund (během běhu)
**QoS:** 0
**Retain:** NO

```json
{
  "timestamp": 1735833760.678,
  "balance": 100.20,
  "equity": 100.45,
  "open_positions": 2,
  "total_trades": 16,
  "winning_trades": 12,
  "losing_trades": 4,
  "win_rate": 0.75,
  "total_pnl": 0.20,
  "max_drawdown": 5.0
}
```

---

#### `polyspike/stats/session`

**Kdy:** Při ukončení bota (shutdown)
**QoS:** 1
**Retain:** YES

```json
{
  "timestamp": 1735837200.901,
  "session_id": "20260102_180000",
  "duration_seconds": 3600,
  "initial_balance": 100.0,
  "final_balance": 105.23,
  "total_pnl": 5.23,
  "total_pnl_pct": 0.0523,
  "total_trades": 25,
  "winning_trades": 18,
  "losing_trades": 7,
  "win_rate": 0.72,
  "max_drawdown": 8.5,
  "avg_win": 0.45,
  "avg_loss": -0.30
}
```

---

## 🔌 Discord Bot Integration Guide

### Připojení k MQTT

#### Python (paho-mqtt)

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        # Subscribe to all topics
        client.subscribe("polyspike/#")
    else:
        print(f"Connection failed: {rc}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = json.loads(msg.payload.decode())

    # Handle different event types
    if "position/opened" in topic:
        handle_position_opened(payload)
    elif "trade/completed" in topic:
        handle_trade_completed(payload)
    # ...

client = mqtt.Client("discord_bot")
client.on_connect = on_connect
client.on_message = on_message

client.connect("localhost", 1883, 60)
client.loop_forever()
```

#### Node.js (mqtt.js)

```javascript
const mqtt = require('mqtt');
const client = mqtt.connect('mqtt://localhost:1883');

client.on('connect', () => {
  console.log('Connected to MQTT broker');
  client.subscribe('polyspike/#');
});

client.on('message', (topic, message) => {
  const payload = JSON.parse(message.toString());

  if (topic.includes('position/opened')) {
    handlePositionOpened(payload);
  }
  // ...
});
```

---

### Doporučené Discord Notifikace

**Kritické (vždy poslat):**

- ✅ `status/bot/started` - Bot se spustil
- ✅ `status/bot/stopped` - Bot se zastavil
- ✅ `status/bot/error` - Kritická chyba
- ✅ `trading/position/opened` - Otevřená pozice
- ✅ `trading/trade/completed` - Dokončený trade (+ P&L)

**Volitelné:**

- ⚠️ `market/spike_detected` - Může být spammy
- ⚠️ `stats/periodic` - Každých 10s (příliš často?)
- ✅ `balance/update` - Každých 12h (OK)
- ✅ `stats/session` - Session summary (při shutdown)

**Heartbeat:**

- ❌ NEposílat do Discordu (každých 30s = spam)
- ✅ Použít pro monitoring (pokud chybí >60s -> alert)

---

### Discord Embed Příklady

#### Position Opened

```python
embed = discord.Embed(
    title="🟢 Position Opened",
    description=payload["market_name"],
    color=0x00ff00,  # Green
    timestamp=datetime.fromtimestamp(payload["timestamp"])
)
embed.add_field(name="Entry Price", value=f"{payload['entry_price']:.4f}")
embed.add_field(name="Size", value=f"${payload['position_size']:.2f}")
embed.add_field(name="Reason", value=payload["reason"])
```

#### Trade Completed

```python
color = 0x00ff00 if payload["pnl"] > 0 else 0xff0000  # Green/Red

embed = discord.Embed(
    title="💰 Trade Completed",
    description=payload["market_name"],
    color=color,
    timestamp=datetime.fromtimestamp(payload["timestamp"])
)
embed.add_field(name="P&L", value=f"${payload['pnl']:+.2f}")
embed.add_field(name="P&L %", value=f"{payload['pnl_pct']*100:+.2f}%")
embed.add_field(name="Duration", value=f"{payload['duration_seconds']}s")
embed.add_field(name="Exit Reason", value=payload["reason"])
```

---

## 🧪 Testování

### Mosquitto CLI Tools

Subscribe to všech zpráv:

```bash
mosquitto_sub -h localhost -t 'polyspike/#' -v
```

Subscribe to specific topic:

```bash
mosquitto_sub -h localhost -t 'polyspike/trading/position/opened' -v
```

Publish test message:

```bash
mosquitto_pub -h localhost -t 'polyspike/status/bot/started' \
  -m '{"timestamp": 1735833600, "session_id": "test"}'
```

---

### Python Test Script

Použij test script:

```bash
# Terminal 1: Subscribe
python test_mqtt.py subscribe

# Terminal 2: Publish test events
python test_mqtt.py publish --event position_opened
```

---

## 📊 Message Frequency

| Event Type | Frequency | Volume |
|------------|-----------|--------|
| heartbeat | 30s | Low |
| spike_detected | Variable | Medium (cca 5-20/min) |
| position/opened | Variable | Low (cca 0-5/min) |
| position/closed | Variable | Low (cca 0-5/min) |
| balance/update | 12h nebo změna | Very Low |
| stats/periodic | 10s | Low |

**Total message volume:** Cca 50-200 zpráv/hodinu (very low load)

---

## ⚠️ Edge Cases

### Missing Fields

Některá pole mohou chybět:

- `spike_magnitude` - může být null pokud není spike
- `market_name` - fallback na truncated token_id pokud API selhalo

**Doporučení:** Vždy použij `.get()` s default value:

```python
market_name = payload.get("market_name", "Unknown Market")
```

---

### Duplicate Messages (QoS 1)

QoS 1 může doručit zprávu vícekrát.

**Řešení:** Track `trade_id` nebo timestamp a ignorovat duplikáty:

```python
seen_trade_ids = set()

if payload["trade_id"] in seen_trade_ids:
    return  # Ignore duplicate
seen_trade_ids.add(payload["trade_id"])
```

---

### Retained Messages

Při připojení dostaneš poslední retained zprávy:

- `status/bot/heartbeat`
- `balance/update`
- `stats/session`

**Řešení:** Ignoruj zprávy starší než 5 minut při startu:

```python
startup_time = time.time()

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)

    # Ignore old retained messages
    if payload["timestamp"] < startup_time - 300:
        return
```

---

## 🔧 Troubleshooting

### Broker není dostupný

```
ERROR: Connection refused [Errno 111]
```

**Řešení:**

1. Zkontroluj že Mosquitto běží: `sudo systemctl status mosquitto`
2. Start Mosquitto: `sudo systemctl start mosquitto`

---

### Žádné zprávy nepřicházejí

1. Zkontroluj že bot běží: `ps aux | grep python.*main.py`
2. Zkontroluj `MQTT_ENABLED=true` v `.env`
3. Zkontroluj mosquitto log: `sudo tail -f /var/log/mosquitto/mosquitto.log`

---

### Zprávy přicházejí ale JSON parse error

1. Zkontroluj payload encoding: `msg.payload.decode('utf-8')`
2. Loguj raw payload před parse: `print(msg.payload)`

---

## 📚 Reference

- [MQTT Protocol](https://mqtt.org/)
- [Paho MQTT Python](https://pypi.org/project/paho-mqtt/)
- [Mosquitto Broker](https://mosquitto.org/)
- [Discord.py Docs](https://discordpy.readthedocs.io/)

---

**Konec dokumentace ✅**
