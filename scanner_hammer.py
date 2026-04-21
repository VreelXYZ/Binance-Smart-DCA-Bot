import time
import os
import ccxt
from dotenv import load_dotenv
from tg_utils import TelegramManager

load_dotenv()

tg = TelegramManager("HAMMER_TG_TOKEN", "HAMMER_TG_CHAT_ID")
SIGNALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hammer_signals.txt')

def main():
    print("🔨 Hammer Scanner started. Monitoring 1m tape, order books, and momentum...")
    
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    exclude_exact = [
        "USDC", "FDUSD", "TUSD", "BUSD", "EUR", "GBP", 
        "USDP", "USDD", "DAI", "AEUR", "TRY", "RUB", "UAH"
    ]
    
    recent_signals = {}
    COOLDOWN_SECONDS = 300 # 5 minutes cooldown per coin

    while True:
        try:
            markets = exchange.load_markets()
            tickers = exchange.fetch_tickers()
            
            candidates = []
            current_time = time.time()
            
            # --- PRE-FILTER: Tickers (Spread and Volume) ---
            for symbol, tick in tickers.items():
                if not symbol.endswith("/USDT") or symbol not in markets: continue
                if not markets[symbol].get('active', False): continue
                
                base_currency = symbol.split('/')[0]
                if base_currency in exclude_exact: continue
                if any(base_currency.endswith(suffix) for suffix in ["UP", "DOWN", "BULL", "BEAR"]): continue
                
                if tick.get('quoteVolume', 0) < 1000000: continue # Min 1M USDT 24h volume
                
                # Spread Protection <= 0.1%
                bid = tick.get('bid', 0)
                ask = tick.get('ask', 0)
                if not bid or not ask or bid == 0: continue
                spread = (ask - bid) / bid
                if spread > 0.002: continue
                
                # Check Cooldown
                if symbol in recent_signals and current_time - recent_signals[symbol] < COOLDOWN_SECONDS:
                    continue
                    
                candidates.append(symbol)

            # --- DEEP FILTER: Momentum & Tape (1m candle) ---
            deep_candidates = []
            for symbol in candidates:
                try:
                    ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=2)
                    if not ohlcv or len(ohlcv) < 2: continue
                    
                    # Use the currently forming live candle (index -1) to catch momentum instantly
                    candle = ohlcv[-1] 
                    c_open = candle[1]
                    c_close = candle[4]
                    total_vol = candle[5]
                    buy_vol = candle[9] # Binance Taker Buy Base Volume
                    sell_vol = total_vol - buy_vol
                    
                    # Condition 3: Momentum (>= 0.1%)
                    if c_open == 0: continue
                    momentum = (c_close - c_open) / c_open
                    if momentum < 0.001: continue
                    
                    # Condition 1: Tape Buy dominance (>= 1.5x)
                    if sell_vol <= 0: sell_vol = 0.0001
                    if buy_vol < sell_vol * 1.5: continue
                    
                    deep_candidates.append((symbol, c_close, momentum, buy_vol, sell_vol))
                    time.sleep(0.05) # Rate limit safety
                except Exception:
                    pass
            
            # --- FINAL FILTER: Order Book Support ---
            match_found = False
            for symbol, current_price, momentum, buy_vol, sell_vol in deep_candidates:
                try:
                    ob = exchange.fetch_order_book(symbol, limit=50)
                    
                    bid_limit = current_price * 0.995 # -0.5% depth
                    ask_limit = current_price * 1.005 # +0.5% depth
                    
                    # Calculate USDT equivalent volume in the book
                    bid_usdt = sum(price * amount for price, amount in ob['bids'] if price >= bid_limit)
                    ask_usdt = sum(price * amount for price, amount in ob['asks'] if price <= ask_limit)
                    
                    if ask_usdt <= 0: ask_usdt = 0.0001
                    
                    # Condition 2: Book Support (Bids >= 1.2x Asks)
                    if bid_usdt >= ask_usdt * 1.2:
                        match_found = True
                        print(f"🔥 EXACT MATCH: {symbol} | Tape: {buy_vol/sell_vol:.1f}x | Book: {bid_usdt/ask_usdt:.1f}x")
                        
                        with open(SIGNALS_FILE, 'a') as f:
                            f.write(f"{symbol}\n")
                            
                        recent_signals[symbol] = current_time
                        
                        tg.send_message(
                            f"🔨 *HAMMER SIGNAL: {symbol}*\n"
                            f"📈 *Momentum (1m):* +{momentum*100:.2f}%\n"
                            f"🛒 *Tape (Buys):* {buy_vol/sell_vol:.1f}x vs Sells\n"
                            f"🧱 *Book (Bids):* {bid_usdt/ask_usdt:.1f}x vs Asks\n"
                            f"💸 *Spread:* < 0.2%"
                        )
                    time.sleep(0.05)
                except Exception as e:
                    print(f"OB Error for {symbol}: {e}")

            if not match_found:
                print("⏳ No suitable coins found. Starting next cycle in 5 seconds...")

            # Fast loop: re-check every 5 seconds to catch real-time 1m changes
            time.sleep(5)
            
        except ccxt.NetworkError as e:
            print(f"Network error: {e}. Retrying in 10s...")
            time.sleep(10)
        except Exception as e:
            print(f"Unexpected error: {e}. Retrying in 10s...")
            time.sleep(10)

if __name__ == "__main__":
    main()
