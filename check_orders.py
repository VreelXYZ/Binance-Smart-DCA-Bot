import ccxt
import os
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'))

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

def main():
    print("Checking active 'traps' (open orders) on Binance...\n")
    try:
        exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'enableRateLimit': True,
            'timeout': 30000,
            'hostname': 'api1.binance.com',
            'options': {
                'adjustForTimeDifference': True,
            }
        })
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return

    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    total_orders = 0

    for symbol in symbols:
        try:
            orders = exchange.fetch_open_orders(symbol)
            if not orders:
                print(f"📭 {symbol}: No open orders (traps are not set).")
                continue
            
            print(f"🎯 {symbol}: Found {len(orders)} active orders:")
            for order in orders:
                side = "🟢 BUY " if order['side'] == 'buy' else "🔴 SELL"
                price = order['price']
                amount = order['amount']
                print(f"    - {side} | Цена: {price} | Объем: {amount}")
            print("-" * 40)
            total_orders += len(orders)
            
        except Exception as e:
            print(f"⚠️ Error fetching orders for {symbol}: {e}")

    print(f"\n✅ Total active traps on exchange: {total_orders}")

if __name__ == '__main__':
    main()