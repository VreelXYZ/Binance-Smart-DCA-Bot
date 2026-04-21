# 🚀 BotTrader: Binance Smart DCA Dual-Strategy Suite

![BotTrader Banner](assets/banner.png)

Tired of staring at charts or missing perfect entries during market swings? **BotTrader** is a professional-grade automated trading system designed exclusively for the **Binance Spot market**. 

This suite features two distinct algorithmic powerhouses, allowing you to switch between **Capital Preservation** and **Aggressive Growth** depending on market volatility.

**If you find this bot useful, please give this repository a Star on GitHub ⭐️! It's just one click for you, but a huge motivation for me to keep pushing updates!**

---

## 🛠 Choose Your Strategy

| Feature | 🛡️ The Conservator | 🔥 The Aggressor | 🔨 The Hammer |
| :--- | :--- | :--- | :--- |
| **Market Focus** | Low Volatility & Swings | High Volatility & Cascades | Extreme Momentum & Micro-Scalps |
| **Logic Priority** | Global Exit & Deep Averaging | Independent Levels Trailing | 100% In/Out & Step Trailing |
| **Grid Depth** | **10 Safety Levels** | **8 Safety Levels** | **No Grid** (Single Order) |
| **Budget Split** | Back-heavy (2.5% to 16.5%) | 20% Base / 10% Safety | 100% All-in per trade |
| **Entry Logic** | 5m Taker Buy Dominance | 5m Taker Buy Dominance | Live 1m Tape, Book & Spread |
| **Trailing Profit** | **Global** (+3.8% Trigger / 0.8% Trail) | **Hard Floor** (0.95% - 1.95%) | **Step Trailing** (+0.25% Ratchet) |
| **Safety Net** | Holds without Stop-Loss | **-10% Stop-Loss** (From Avg) | **-0.22% Stop** (Daily limit: 3) |

---

### 🛡️ The Conservator (`bot_conservator.py`)
*Designed for stability, deep averaging, and Global Swing exits.*

*   **Global DCA Swing Logic:** Instead of selling individual levels, this bot calculates the True Average Entry price of the entire position. It waits for the whole basket to reach a profitable target before exiting everything at once.
*   **Deep 10-Level Grid:** Employs a comprehensive 10-step safety grid to heavily average down the entry price during continuous market drops.
*   **Back-heavy Budget Allocation:** Uses dynamic percentages (from 2.5% on the base up to 16.5% on the deepest levels), ensuring maximum capital is deployed at the best possible prices.
*   **Global Trailing Profit:** 
    *   **Trigger:** +3.8% from the True Average Entry.
    *   **Callback:** 0.8% deviation from the local peak.
*   **No Stop-Loss (Hold & Swing):** Relies purely on deep DCA logic to ride out volatility and eventually exit the entire position in profit, preventing realized losses on strong dumps.

### 🔥 The Aggressor (`bot_aggressor.py`)
*Designed for high-volatility scalping and rapid cascade execution.*

*   **Independent Trailing:** Every single grid level is treated independently. The bot scales out of positions step-by-step as the price bounces.
*   **Expanding Grid:** Covers a logarithmic price range (`[0.9%, 0.9%, 1.2%, ... 3.5%]`) to catch micro-jumps early and hold deep dumps later.
*   **Hard Floor Profit:** Protected trailing secures at least +0.90% to +1.90% profit minimum once the initial targets are met.
*   **Cascade Re-Entry:** When a lower level is sold, the bot dynamically recalculates and replaces the entry limit order from the exact sale price, riding the wave.
*   **Emergency Stop-Loss:** Features a strict -10% hard stop-loss from the true average entry price to cut losses during catastrophic crashes.

### 🔨 The Hammer (`bot_hammer.py`)
*Designed for lightning-fast WebSocket scalping and momentum riding.*

*   **100% In/Out Execution:** Trades the allocated budget in a single market order. No DCA grids or averaging.
*   **Live WebSocket Tracking:** Connects to Binance via `ccxt.pro` WebSockets for millisecond-level price tracking.
*   **Dynamic Step Trailing:** Base stop at -0.22%. As profit grows, the stop loss ratchets up in +0.22% steps (e.g., +0.44% profit moves the stop to +0.22%).
*   **Daily Stop-Loss:** Automatically shuts down if it hits 3 consecutive stop-losses to protect capital during choppy markets.
*   **Cumulative Profit Tracking:** Saves and reports overall bot profit locally and via Telegram after every trade.

###  Market Scanner (`scanner.py`)
*The High-Frequency "Bloodhound" Radar for finding instant pump momentum.*

*   **Tape Dominance (1m):** Analyzes the live, forming 1-minute candle. Triggers only if Market Buys exceed Market Sells by $\ge$ 2.5x.
*   **Order Book Support:** Scans the order book at 0.5% depth. The Buy Wall (Bids) must be $\ge$ 2x thicker than the Sell Wall (Asks).
*   **Spread & Momentum Filter:** Rejects coins with a spread > 0.1% and requires a live price jump of $\ge$ 0.1%.
*   **Hammer Integration:** Drops instantaneous signals into a local file for the Hammer bot to execute without API latency.

---

## 🧠 Core Engineering Features

Both strategies are built upon a resilient, high-performance core:

1.  **Advanced Trailing Logic**: Depending on the strategy, the bot either tracks each level independently (Aggressor) or trails the true average of the entire basket (Conservator), always riding the trend to maximize profit instead of using fixed targets.
2.  **Volume Filter (Bull Trap Shield)**: Before any entry, the bots analyze the **5-minute Taker Volume**. They only enter when buying pressure significantly outweighs selling pressure.
3.  **Auto Grid Restoration & Phantom Order Cleanup**: If a limit order is manually canceled on the exchange or lost, the bots detect the missing order (`OrderNotFound`), clear it from memory, and seamlessly repair the grid hole by calculating and placing a new limit order at the exact required level.
4.  **Market Cooling (Radar Mode)**: After a successful exit, the bots enter a cooldown phase, waiting for a localized dip or time expiry before re-entering to prevent FOMO buying at the local top.
5.  **Hot Reload & Emergency Exits**: Update symbols, budget, or move coins to the EXIT list in `.env` on the fly. The bot reads changes instantly without needing a restart.
6.  **Live Status Reporting via Telegram**: Get a detailed, real-time report of all active positions by sending the `/status` command. The report includes average entry price, PNL, bought levels, active limit orders, and accumulated profit for each symbol.

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

# HAMMER & SCANNER CONFIG
HAMMER_API_KEY=your_api_key_3
HAMMER_SECRET_KEY=your_secret_key_3
HAMMER_BUDGET_USDT=100
HAMMER_TG_TOKEN=your_tg_token_3
HAMMER_TG_CHAT_ID=your_chat_id_3
```

### 3. Execution
```bash
# Run the safe compounder
python bot_conservator.py

# Run the high-volatility hunter
python bot_aggressor.py

# Run the targeted strikes on the market
python start_hammer.py
```

---

## ⚠️ Disclaimer
Trading cryptocurrency involves significant risk. This software is provided "as is" for educational purposes. Always test with a small budget first. Ensure **"Enable Withdrawals"** is disabled on your API keys for maximum security.

*Profit from volatility. Trust the algorithm.*
