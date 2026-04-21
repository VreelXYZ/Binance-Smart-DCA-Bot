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
            # --- HOT RELOAD ENV ---
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)
            if os.getenv('HAMMER_STATUS', 'RUNNING').upper() == 'STOP':
                print("🛑 STOP status detected in .env. Scanner shutting down.")
                break
                
            markets = exchange.load_markets()
            tickers = exchange.fetch_tickers()
            
            candidates = []
            current_time = time.time()
            
            stats = {'evaluated': 0, 'fail_trend': 0, 'fail_vol': 0, 'fail_spread': 0, 'fail_15m': 0, 'fail_momentum': 0, 'fail_tape': 0, 'fail_book': 0, 'api_errors': 0, 'ob_errors': 0}
            
            # --- PRE-FILTER: Tickers (Spread and Volume) ---
            for symbol, tick in tickers.items():
                if not symbol.endswith("/USDT") or symbol not in markets: continue
                if not symbol.isascii(): continue
                if not markets[symbol].get('active', False): continue
                
                base_currency = symbol.split('/')[0]
                if base_currency in exclude_exact: continue
                if any(base_currency.endswith(suffix) for suffix in ["UP", "DOWN", "BULL", "BEAR"]): continue
                
                stats['evaluated'] += 1
                
                # Macro Trend Filter: Coin MUST be in a daily uptrend (at least +3.0% over 24h)
                pct_change = tick.get('percentage', 0)
                if pct_change is None or pct_change < 3.0:
                    stats['fail_trend'] += 1
                    continue
                
                if tick.get('quoteVolume', 0) < 1000000: 
                    stats['fail_vol'] += 1
                    continue # Min 1M USDT 24h volume
                
                # Spread Protection <= 0.1%
                bid = tick.get('bid', 0)
                ask = tick.get('ask', 0)
                if not bid or not ask or bid == 0: continue
                spread = (ask - bid) / bid
                if spread > 0.002: 
                    stats['fail_spread'] += 1
                    continue
                
                # Check Cooldown
                if symbol in recent_signals and current_time - recent_signals[symbol] < COOLDOWN_SECONDS:
                    continue
                    
                candidates.append(symbol)

            # --- DEEP FILTER: Momentum & Tape (1m candle) ---
            deep_candidates = []
            for symbol in candidates:
                try:
                    market_id = exchange.market(symbol)['id']
                    res = exchange.publicGetKlines({'symbol': market_id, 'interval': '1m', 'limit': 15})
                    
                    time.sleep(0.05) # Delay IMMEDIATELY after request to avoid skipping it via continue
                    
                    if not res or len(res) < 15: continue
                    
                    # 15-Minute Macro-Volume Filter (Avoid buying into a downtrend dump)
                    total_vol_15m = sum(float(c[5]) for c in res)
                    buy_vol_15m = sum(float(c[9]) for c in res)
                    sell_vol_15m = total_vol_15m - buy_vol_15m
                    
                    if sell_vol_15m > buy_vol_15m:
                        stats['fail_15m'] += 1
                        continue
                    
                    # Use the currently forming live candle (index -1) to catch momentum instantly
                    candle = res[-1] 
                    c_open = float(candle[1])
                    c_close = float(candle[4])
                    total_vol = float(candle[5])
                    buy_vol = float(candle[9]) # Binance Taker Buy Base Volume
                    sell_vol = total_vol - buy_vol
                    
                    # Condition 3: Momentum (>= 0.1%)
                    if c_open == 0: continue
                    momentum = (c_close - c_open) / c_open
                    if momentum < 0.0015: # Restored to 0.15% 
                        stats['fail_momentum'] += 1
                        continue
                    
                    # Condition 1: Tape Buy dominance (>= 1.5x)
                    if sell_vol <= 0: sell_vol = 0.0001
                    if buy_vol < sell_vol * 1.5: 
                        stats['fail_tape'] += 1
                        continue
                    
                    deep_candidates.append((symbol, c_close, momentum, buy_vol, sell_vol))
                except Exception as e:
                    stats['api_errors'] += 1
                    print(f"⚠️ [API ERROR] 1m data fetch failed for {symbol}: {e}")
                    time.sleep(0.05) # Delay even on error to prevent rate limit loops
            
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
                            f"🔨 *SIGNAL: {symbol}*\n"
                            f"📈 *Momentum (1m):* +{momentum*100:.2f}%\n"
                            f"🛒 *Tape (Buys):* {buy_vol/sell_vol:.1f}x vs Sells\n"
                            f"🧱 *Book (Bids):* {bid_usdt/ask_usdt:.1f}x vs Asks\n"
                            f"💸 *Spread:* < 0.2%"
                        )
                    else:
                        stats['fail_book'] += 1
                    time.sleep(0.05)
                except Exception as e:
                    stats['ob_errors'] += 1
                    print(f"⚠️ [OB ERROR] Order book fetch failed for {symbol}: {e}")

            if not match_found:
                print("⏳ No suitable coins found. Starting next cycle in 5 seconds...")
                
            print(f"📊 [DEBUG] Checked: {stats['evaluated']} | Trend: {stats['fail_trend']} | Vol: {stats['fail_vol']} | Spread: {stats['fail_spread']} | 15m: {stats['fail_15m']} | Momentum: {stats['fail_momentum']} | Tape: {stats['fail_tape']} | Book: {stats['fail_book']} | Err: {stats['api_errors'] + stats['ob_errors']}")

            total_errors = stats['api_errors'] + stats['ob_errors']
            if total_errors > 0:
                tg.send_message(f"⚠️ *Scanner Warning*\nEncountered {total_errors} API/OB errors in the last cycle.\nPlease check the terminal for details.")

            # Fast loop: re-check every 5 seconds to catch real-time 1m changes
            time.sleep(5)
            
        except ccxt.NetworkError as e:
            print(f"🚨 Network error: {e}. Retrying in 10s...")
            tg.send_message(f"🚨 *Scanner Network Error:*\n`{e}`\nRetrying in 10s...")
            time.sleep(10)
        except Exception as e:
            print(f"🚨 Unexpected error: {e}. Retrying in 10s...")
            tg.send_message(f"🚨 *Scanner Critical Error:*\n`{e}`\nRetrying in 10s...")
            time.sleep(10)

if __name__ == "__main__":
    main()
