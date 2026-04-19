# 🚀 BotTrader: Binance Smart DCA Dual-Strategy Suite

![BotTrader Banner](assets/banner.png)

Tired of staring at charts or missing perfect entries during market swings? **BotTrader** is a professional-grade automated trading system designed exclusively for the **Binance Spot market**. 

This suite features two distinct algorithmic powerhouses, allowing you to switch between **Capital Preservation** and **Aggressive Growth** depending on market volatility.

**If you find this bot useful, please give this repository a Star on GitHub ⭐️! It's just one click for you, but a huge motivation for me to keep pushing updates!**

---

## 🛠 Choose Your Strategy

| Feature | 🛡️ The Conservator | 🔥 The Aggressor |
| :--- | :--- | :--- |
| **Market Focus** | Low-to-Medium Volatility | High Volatility & Deep Dips |
| **Logic Priorirty** | Capital Protection & Steady Growth | Maximum Accumulation & "Moon" Trailing |
| **Grid Depth** | **5 Safety Levels** (6 orders total) | **8 Safety Levels** (9 orders total) |
| **Budget Split** | 20% Base / 16% per Safety Order | 20% Base / 10% per Safety Order |
| **Entry Gaps** | Tight (0.4% - 1.0% steps) | **Expanding** (0.9% to 3.5% steps) |
| **Trailing Profit** | **Hard Floor** (0.6% - 1.0%) | **Hard Floor** (0.95% - 1.95%) |
| **Safety Net** | Shallow grid for quick profit resets | **-10% Stop-Loss** (~15.5% from Base entry) |

---

### 🛡️ The Conservator (`bot_conservator.py`)
*Designed for stability and compound growth.*

*   **Quick Resets:** Tighter trailing targets ensure the bot exits positions quickly when a trend reverses, keeping capital liquid.
*   **Elastic Grid:** Uses dynamic distancing between safety orders to optimize entry prices during minor pullbacks.
*   **Sensitive Trailing:** 
    *   **Base:** +1.0% trigger / 0.3% callback.
    *   **Safety Orders:** +0.55% trigger / 0.15% callback (~0.4% net profit).

*   **Expanding Grid:** Covers a logarithmic price range (`[0.009, 0.009, 0.012, 0.015, 0.019, ... 0.035]`) to catch micro-jumps early and hold deep dumps later.
*   **Protected Profit:** Protected trailing aims to secure at least **+0.9%** profit once triggered (subject to market slippage).
*   **Full Capital Deployment:** Includes a hard Stop-Loss at **-10% from Average Entry Price** (protects up to a total ~15.5% dump).
*   **Aggressive Hard Floor:**
    *   **Level 0 (Base):** 1.95% trigger / 0.5% callback / **1.90% Floor**.
    *   **Levels 1-8 (Safety):** 0.95% trigger / 0.3% callback / **0.90% Floor**.

### 🛡️ The Conservator (`bot_conservator.py`)
*Designed for stability and rapid compounding.*

*   **Quick Turnaround:** Tighter targets ensure capital stays liquid for the next opportunity.
*   **Conservative Hard Floor:**
    *   **Level 0 (Base):** 1.0% trigger / 0.3% callback / **0.95% Floor**.
    *   **Levels 1-5 (Safety):** 0.6% trigger / 0.2% callback / **0.55% Floor**.

### 📡 Market Scanner (`scanner.py`)
*The "Bloodhound" Radar for finding pump candidates.*

*   **24h Guard:** Only scans coins with 0% to +15% daily growth to avoid buying at the absolute peak.
*   **Volume Spike Detection:** Alerts when a 5-minute candle's volume is $\ge$ 3x the recent average.
*   **Momentum Confirmation:** Requires a minimum +1.5% price jump within a single 5-minute candle.
*   **Aggressor Integration:** Sends instant alerts to the Aggressor Telegram bot for manual or automated oversight.

---

## 🧠 Core Engineering Features

Both strategies are built upon a resilient, high-performance core:

1.  **Independent Trailing Take Profit**: Every DCA level (Base and all Safety Orders) tracks the price upwards independently. The bot doesn't just sell at a fixed percentage; it rides the trend until exhaustion.
2.  **Volume Filter (Bull Trap Shield)**: Before any entry, the bot analyzes the **5-minute Taker Volume**. It only enters when buying pressure significantly outweighs selling pressure.
3.  **Dynamic Cascade Re-Entry**: When a safety level is sold, the bot dynamically re-places the entry order based on the actual sale price, maintaining mathematical grid integrity without overlap.
4.  **Auto Grid Restoration & Phantom Order Cleanup**: On startup or during execution, if a limit order is manually canceled on the exchange or lost, the bot detects the missing order (`OrderNotFound`), clears it from local memory, and seamlessly repairs the grid hole by calculating and placing a new limit order at the exact required level.
5.  **Market Cooling & Hot Reload**: After a Base Sale, the bot enters "Radar Mode" to prevent FOMO. Update symbols, budget, or emergency exits in `.env` instantly without restart.
6.  **Live Status Reporting via Telegram**: Get a detailed, real-time report of all active positions by sending the `/status` command to the bot. The report includes average entry price, PNL, bought levels, and active limit orders for each symbol.

---

## 📊 Setup & Deployment

### 1. Installation
```bash
# Clone the repository
git clone https://github.com/VreelXYZ/Binance-Smart-DCA-Bot.git
cd Binance-Smart-DCA-Bot

# Install required libraries
pip install ccxt python-dotenv requests
```

### 2. Configuration (`.env`)
Create a `.env` file in the root directory. You can run one or both bots simultaneously.

```env
# BINANCE CORE
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key

# CONSERVATOR CONFIG
CONSERVATOR_SYMBOLS=BTC/USDT,ETH/USDT
TOTAL_BUDGET_USDT_CONSERVATOR=1000
TG_TOKEN=your_tg_token
TG_CHAT_ID=your_chat_id

# AGGRESSOR CONFIG
AGGRESSOR_SYMBOLS=SOL/USDT,BNB/USDT
TOTAL_BUDGET_USDT=500
AGGRESSOR_TG_TOKEN=your_tg_token_2
AGGRESSOR_TG_CHAT_ID=your_chat_id_2
```

### 3. Execution
```bash
# Run the safe compounder
python bot_conservator.py

# Run the high-volatility hunter
python bot_aggressor.py

# Run the pump radar
python scanner.py
```

---

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This software is provided "as is" for educational purposes. Always test with a small budget first. Ensure **"Enable Withdrawals"** is disabled on your API keys for maximum security.

*Profit from volatility. Trust the algorithm.*
