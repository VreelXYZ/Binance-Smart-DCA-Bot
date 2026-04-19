import time
import datetime
import os
import requests
import ccxt
from dotenv import load_dotenv
from tg_utils import TelegramManager

# Load environment variables
load_dotenv()

tg = TelegramManager("AGGRESSOR_TG_TOKEN", "AGGRESSOR_TG_CHAT_ID")
send_telegram_message = tg.send_message

def main():
    print("Radar successfully started. Scanning markets...")
    
    # Initialize CCXT Binance instance without API keys
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {
        'defaultType': 'spot'
        }
    })
    
    # Exclude exact stablecoins and fiats
    exclude_exact = [
        "USDC", "FDUSD", "TUSD", "BUSD", "EUR", "GBP", 
        "USDP", "USDD", "DAI", "AEUR", "TRY", "RUB", "UAH"
    ]

    while True:
        try:
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting new scan cycle...")

            # Step 1: Reload markets to get the latest list of tradable pairs.
            # This is crucial for a long-running script to avoid using stale data (e.g., delisted pairs).
            markets = exchange.load_markets(reload=True)

            # Step 2: Get all tickers for the spot market.
            tickers = exchange.fetch_tickers()
            candidates = []
            
            for symbol, ticker_info in tickers.items():
                if symbol not in markets:
                    continue
                
                market = markets[symbol]
                if not market.get('active', False) or not market.get('spot', False):
                    continue

                if not symbol.endswith("/USDT"):
                    continue
                    
                base_currency = symbol.split('/')[0]
                
                # Exclude specific tokens (Stablecoins, margins)
                if base_currency in exclude_exact:
                    continue
                if any(base_currency.endswith(suffix) for suffix in ["UP", "DOWN", "BULL", "BEAR"]):
                    continue
                
                # FILTER 3: ALL-TIME-HIGH PROTECTION
                change_24h = ticker_info.get('percentage')
                if change_24h is None:
                    continue
                
                if -10 <= change_24h <= 20:
                    quote_volume_24h = ticker_info.get('quoteVolume')
                    if quote_volume_24h and quote_volume_24h > 1000000:
                        candidates.append((symbol, change_24h))
            
            print(f"Found {len(candidates)} candidates matching 24h and volume filters.")
            
            for symbol, change_24h in candidates:
                try:
                    # Step 3: Fetch 5m candles (OHLCV)
                    # To get last closed and previous 10, we retrieve 12 total.
                    # Index -1: current (unclosed) candle
                    # Index -2: last closed candle
                    # Index -12 to -3: previous 10 closed candles
                    ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=12)
                    
                    if not ohlcv or len(ohlcv) < 12:
                        continue
                    
                    last_closed = ohlcv[-2]
                    prev_10 = ohlcv[-12:-2]
                    
                    lc_open = last_closed[1]
                    lc_close = last_closed[4]
                    lc_volume = last_closed[5]
                    
                    if lc_open == 0:
                        continue
                        
                    # FILTER 2: BUYER FILTER (Green candle + 1.5% minimum growth)
                    growth_5m = ((lc_close - lc_open) / lc_open) * 100
                    if growth_5m < 1.5:
                        continue
                        
                    # FILTER 1: VOLUME FILTER (Min 3x average of previous 10)
                    avg_volume = sum([c[5] for c in prev_10]) / 10
                    if avg_volume == 0:
                        continue
                        
                    vol_multiplier = lc_volume / avg_volume
                    
                    if vol_multiplier >= 3:
                        # ALL CONDITIONS MET
                        msg = (
                            f"🚨 RADAR: Pump Initiating!\n"
                            f"💎 Coin: {symbol}\n"
                            f"� Volume jumped {vol_multiplier:.1f}x!\n"
                            f"📈 5 min growth: +{growth_5m:.2f}%\n"
                            f"🕒 Overall growth (24h): +{change_24h:.2f}%"
                        )
                        print(f"Signal generated for {symbol}!")
                        send_telegram_message(msg)
                        
                except requests.exceptions.RequestException as e:
                    print(f"Network error while fetching OHLCV for {symbol}: {e}")
                except Exception as e:
                    print(f"Unexpected error processing {symbol}: {e}")
                    
                # Small sleeper to respect rate limits
                time.sleep(0.05)

            print("Scan cycle complete. Waiting 5 minutes for the next cycle...")
            time.sleep(300)

        except ccxt.NetworkError as e:
            print(f"Binance network error: {e}. Retrying in 60 seconds...")
            time.sleep(60)
        except ccxt.ExchangeError as e:
            print(f"Binance exchange error: {e}. Retrying in 60 seconds...")
            time.sleep(60)
        except Exception as e:
            print(f"Unexpected cycle error: {e}. Retrying in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main()
