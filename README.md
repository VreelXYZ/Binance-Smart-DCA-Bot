# 🚀 BotTrader: Binance Smart DCA Dual-Strategy Suite

![BotTrader Banner](assets/banner.png)

Tired of staring at charts or missing perfect entries during market swings? **BotTrader** is a professional-grade automated trading system designed exclusively for the **Binance Spot market**. 

This suite features two distinct algorithmic powerhouses, allowing you to switch between **Capital Preservation** and **Aggressive Growth** depending on market volatility.

---

## 🛠 Choose Your Strategy

| Feature | 🛡️ The Conservator | 🔥 The Aggressor |
| :--- | :--- | :--- |
| **Market Focus** | Low-to-Medium Volatility | High Volatility & Deep Dips |
| **Logic Priorirty** | Capital Protection & Steady Growth | Maximum Accumulation & "Moon" Trailing |
| **Grid Depth** | **5 Safety Levels** (6 orders total) | **8 Safety Levels** (9 orders total) |
| **Budget Split** | 20% Base / 16% per Safety Order | 20% Base / 10% per Safety Order |
| **Entry Gaps** | Tight (0.4% - 1.0% steps) | Fixed **1.9% steps** (Deep coverage) |
| **Trailing Profit** | Sensitive (0.55% - 1.0% trigger) | Aggressive (**1.9% - 3.0% trigger**) |
| **Safety Net** | Shallow grid for quick profit resets | **-10% Stop-Loss** (~16.3% from Base entry) |

---

### 🛡️ The Conservator (`bot_conservator.py`)
*Designed for stability and compound growth.*

*   **Quick Resets:** Tighter trailing targets ensure the bot exits positions quickly when a trend reverses, keeping capital liquid.
*   **Elastic Grid:** Uses dynamic distancing between safety orders to optimize entry prices during minor pullbacks.
*   **Sensitive Trailing:** 
    *   **Base:** +1.0% trigger / 0.3% callback.
    *   **Safety Orders:** +0.55% trigger / 0.15% callback (~0.4% net profit).

### 🔥 The Aggressor (`bot_aggressor.py`)
*Designed for high-reward capture during market turbulence.*

*   **Deep Value:** Covers a wide price range (8 levels at 1.9% each) to catch deep corrections, covering up to **~14.6%** drop.
*   **Runaway Profits:** Higher trailing targets allow the bot to ride strong momentum for maximum gains.
*   **Safety Buffer:** Includes a hard Stop-Loss at **-10% from Average Entry Price** (protects up to a total ~16.3% dump).
*   **Aggressive Trailing:**
    *   **Base:** +3.0% trigger / 0.5% callback.
    *   **Safety Orders:** +1.9% trigger / 0.4% callback.

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
4.  **Radar Mode & Market Cooling**: After a successful Base Sale, the bot enters "Radar Mode" for 5 minutes (or until a 1% price drop), preventing immediate FOMO re-entry.
5.  **Hot Reload System**: Update your trading list, budget, or emergency exit list in the `.env` file, and the bot applies changes instantly without a restart.

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
