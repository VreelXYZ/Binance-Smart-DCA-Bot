# 🚀 Binance Smart DCA Bot: Master the Spot Market on Autopilot

Tired of staring at charts, missing perfect entry points, or getting stuck in sudden market dips? Meet your new automated trading powerhouse, designed exclusively for the **Binance Spot market**.

This isn't just another basic grid bot. It’s a highly adaptive algorithmic trading assistant built on a dual-strategy engine, designed to maximize your gains during bull runs and protect your capital during sudden crashes.

## 🧠 How It Works: The Dual-Strategy Engine

My bot treats the market like a professional trader, using a sophisticated separation between **Base Entries** and **Safety Nets**:

* **The Base Order (Level 0):** When the market is stable or growing, the bot enters a position at the current market price. Instead of setting a boring, fixed target, it activates a **Wide Trailing Take Profit**. It lets your winning trades run, tracking the price upwards, and only executes a market sell when the trend exhausts and pulls back. *Result: You catch the massive moonshots, not just breadcrumbs.*
* **The Dynamic Safety Grid (Levels 1, 2, 3...):** Crypto is volatile. If the market suddenly dumps, the bot doesn't panic. It deploys a series of limit buy orders below your entry. But here is the magic: the grid is **dynamic**. Instead of rigid 1% steps, the gaps expand as the price falls (e.g., -0.5%, -1.5%, -3.0%). It catches falling knives safely without draining your USDT budget too early.
* **Quick-Escape Trailing for Drawdowns:** When the bot buys a dip via a Safety Order, it switches to a **Tight Trailing Take Profit**. At the very first sign of a market bounce, it quickly locks in a small profit and frees up your frozen capital.

## ✨ Key Features at a Glance

* 🛡️ **Adaptive DCA Strategy:** Buys the dip intelligently with expanding grid steps.
* 📈 **Smart Trailing Take Profit:** Different trailing configurations for your Base Orders (to maximize huge gains) and Safety Orders (to quickly escape drawdowns).
* 📱 **Live Telegram Integration:** You are never left in the dark. Connect your Telegram bot to receive instant, beautifully formatted reports on executed trades, cycle completions, and system status directly to your phone.
* 🔒 **100% Secure & Local:** Your funds stay on your exchange. The bot uses API keys stored safely in a hidden `.env` file on your local machine. No third-party servers, no hidden fees.

*Take emotions out of the equation. Let the math do the heavy lifting.*

---

## 🛠 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/VreelXYZ/Binance-Smart-DCA-Bot.git](https://github.com/VreelXYZ/Binance-Smart-DCA-Bot.git)
   cd Binance-Smart-DCA-Bot
   ```

2. **Install dependencies:**
   The bot requires `ccxt` for exchange connection, `python-dotenv` for hidden variables, and `requests` for Telegram alerts.
   ```bash
   pip install ccxt python-dotenv requests
   ```

3. **Configure API Keys:**
   * Copy the `.env.example` file and rename it to `.env`.
   * Open the new `.env` file and insert your Binance and Telegram credentials:
     ```env
     BINANCE_API_KEY=your_binance_api_key_here
     BINANCE_SECRET_KEY=your_binance_secret_key_here
     TG_TOKEN=your_telegram_bot_token_here
     TG_CHAT_ID=your_telegram_chat_id_here
     ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

## ⚠️ Disclaimer
This bot trades with real funds. The author is not responsible for any financial losses. It is highly recommended to test the algorithm with a small budget first. Ensure that your Binance API key has "Spot & Margin Trading" enabled, and **"Enable Withdrawals" strictly disabled**.
