# 🏹 PolySpike Hunter - Quick Start Guide

## 📋 Co je potřeba před spuštěním

### 1. Vytvoř `.env` soubor

```bash
cp .env.example .env
```

### 2. Nastav Polymarket API klíče v `.env`

```bash
# Pokud nemáš API klíče, můžeš použít fake pro paper trading
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
```

**POZNÁMKA:** V paper trading modu se NEPOSÍLAJÍ žádné reálné obchody, takže API klíč není nutný pro základní testování. Pokud chceš ale získávat reálná data z Polymarket, musíš mít platný klíč.

### 3. Nainstaluj závislosti

```bash
pip install -r requirements.txt
```

## 🚀 Spuštění Bota

### Jednoduchý způsob:

```bash
python run_bot.py
```

### Nebo přímý způsob:

```bash
python main.py
```

## ⚙️ Konfigurace

Veškeré nastavení je v `.env` souboru:

```bash
# Paper Trading nastavení
PAPER_TRADING=true              # Zapnout paper trading (simulace)
INITIAL_BALANCE=100.0           # Počáteční balance ($100)
MIN_POSITION_SIZE=1.0           # Minimální velikost pozice
MAX_OPEN_POSITIONS=10           # Max současně otevřených pozic

# Trading strategie
SPIKE_THRESHOLD=0.03            # 3% spike pro vstup do pozice
POSITION_SIZE=5.0               # Velikost pozice ($5)
STOP_LOSS_PCT=0.02              # 2% stop loss
TAKE_PROFIT_PCT=0.04            # 4% take profit
MAX_DRAWDOWN=50.0               # Max ztráta před zastavením ($50)

# Market monitoring
MONITOR_STRATEGY=volume         # Strategie výběru trhů (volume/random/manual)
MAX_MONITORED_MARKETS=50        # Počet sledovaných trhů
MIN_MARKET_VOLUME=1000.0        # Minimální objem trhu
POLL_INTERVAL=1.0               # Interval pollingu (sekundy)

# Logging
LOG_LEVEL=INFO                  # DEBUG/INFO/WARNING/ERROR
```

## 📊 Výstupy

Po spuštění bota se vytvoří složka `data/sessions/TIMESTAMP/` s:

- **`trades.json`** - Všechny dokončené obchody (JSON)
- **`markets.csv`** - Průběžná data o sledovaných trzích (CSV)
- **`summary.json`** - Souhrn session na konci

## 🛑 Zastavení

Stiskni **Ctrl+C** pro graceful shutdown. Bot zobrazí statistiky session.

## 📈 Co bot dělá:

1. **Připojí se** k Polymarket API
2. **Vybere 50 nejlikvidnějších trhů** (podle volume)
3. **Sleduje ceny každou sekundu** 
4. **Detekuje spiky** (prudké pohyby cen ±3%)
5. **Vstupuje do pozice** při detekci spiku
6. **Vystupuje** při:
   - Take profit (4% zisk)
   - Stop loss (2% ztráta)
7. **Loguje vše** do CSV/JSON souborů

## ⚠️ DŮLEŽITÉ

- ✅ **Paper trading = simulace**, žádné reálné peníze
- ✅ **Reálná tržní data** z Polymarket API
- ✅ **Fake balance** ($100 na začátku)
- ❌ **Žádné skutečné obchody**

## 🔧 Troubleshooting

### "Configuration error: POLYMARKET_PRIVATE_KEY"

Vytvoř `.env` soubor a nastav fake private key:
```bash
POLYMARKET_PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
```

### Bot se nespustí / import errors

Ujisti se že jsi v root složce projektu a že máš nainstalované dependencies:
```bash
pip install -r requirements.txt
```

### Žádná tržní data

Zkontroluj připojení k internetu a dostupnost Polymarket API.

## 📚 Další info

- Více detailů v `README.md`
- Architektura v `AGENTS.md`
- Technické specifikace v source kódu
