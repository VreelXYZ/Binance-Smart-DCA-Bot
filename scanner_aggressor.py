import ccxt
import os
import time
from dotenv import load_dotenv
from tg_utils import TelegramManager

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'), override=True)

# Connect to the Aggressor's Telegram bot
tg = TelegramManager('AGGRESSOR_TG_TOKEN', 'AGGRESSOR_TG_CHAT_ID')

def main():
    print("🔍 Starting the flat range scanner for Aggressor...")
    
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    
    # 2. Exclude stablecoins, fiat, and heavyweights/commodities
    exclude_exact = [
        "USDC", "FDUSD", "TUSD", "BUSD", "EUR", "GBP", 
        "USDP", "USDD", "DAI", "AEUR", "TRY", "RUB", "UAH",
        "XAUT", "PAXG", "BTC", "WBTC", "SOL", "ETH"
    ]
    
    candidates = []
    
    # 3. Filter by volume
    for symbol, tick in tickers.items():
        if not symbol.endswith("/USDT") or symbol not in markets: continue
        if not markets[symbol].get('active', False): continue
        
        base_currency = symbol.split('/')[0]
        if base_currency in exclude_exact: continue
        if any(base_currency.endswith(suffix) for suffix in ["UP", "DOWN", "BULL", "BEAR"]): continue
        
        vol = tick.get('quoteVolume', 0)
        if vol < 2000000: continue # Minimum daily volume 2M USDT
        
        candidates.append((symbol, vol))
        
    print(f"📊 Found {len(candidates)} coins with volume > 2M USDT. Checking 14-day chart...")
    
    results = []
    for symbol, vol in candidates:
        try:
            # 4. Load daily candles (last 14 days)
            ohlcv = exchange.fetch_ohlcv(symbol, '1d', limit=14)
            if not ohlcv or len(ohlcv) < 14: continue
            
            highs = [candle[2] for candle in ohlcv]
            lows = [candle[3] for candle in ohlcv]
            
            max_high = max(highs)
            min_low = min(lows)
            
            if min_low == 0: continue
            
            # 5. Corridor width
            width_pct = ((max_high - min_low) / min_low) * 100
            
            # Keep only corridors between 5% and 15%
            if 5 <= width_pct <= 15:
                # 6. Current price position (using the last candle's close price)
                current_price = ohlcv[-1][4]
                pos_pct = ((current_price - min_low) / (max_high - min_low)) * 100
                
                # Condition: not at the bottom and not at the peak (from 20% to 80%)
                if 20 <= pos_pct <= 80:
                    results.append({'symbol': symbol, 'width': width_pct, 'pos': pos_pct, 'vol': vol})
            
            time.sleep(0.05) # Rate limit safety
        except Exception as e:
            print(f"Error with {symbol}: {e}")
            
    # 7. Sort by channel width (narrowest first) and output Top-20
    results.sort(key=lambda x: x['width'])
    top_20 = results[:20]
    
    if not top_20:
        msg = "🤷‍♂️ Scanner: No suitable coins found in a flat range (5-15% corridor)."
    else:
        msg = "📊 *Top 20 coins in a flat range (Aggressor)*\n_Range: 5-15% | Position: 20-80%_\n\n"
        for idx, item in enumerate(top_20, 1):
            sym = item['symbol'].replace('/USDT', '')
            msg += f"{idx}. *{sym}* | ↕️ {item['width']:.2f}% | 💰 {item['vol']/1000000:.1f}M\n   └ Position: {item['pos']:.1f}%\n"
            
    print("\n" + msg)
    tg.send_message(msg)

if __name__ == "__main__":
    main()