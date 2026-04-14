import ccxt
import sys
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

def main():
    print("🚨 EMERGENCY SELL (PANIC SELL) 🚨")
    confirm = input("Are you sure you want to cancel all orders and market sell everything? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled. Exiting.")
        sys.exit(0)

    try:
        exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': SECRET_KEY,
            'enableRateLimit': True,
        })
        exchange.load_markets()
    except Exception as e:
        print(f"❌ Binance connection error: {e}")
        sys.exit(1)

    coins = ['BTC', 'ETH', 'SOL']
    print("\nStarting emergency sell-off...")

    for coin in coins:
        symbol = f"{coin}/USDT"
        print(f"\n[{coin}] Processing coin...")
        
        # 1. Cancel all orders for the pair
        try:
            exchange.cancel_all_orders(symbol)
            print(f"  ✅ All open orders for {symbol} successfully cancelled.")
        except ccxt.ExchangeError as e:
            if "-2011" in str(e):
                print(f"  ℹ️ No open orders to cancel for {symbol}.")
            else:
                print(f"  ⚠️ Error cancelling orders for {symbol}: {e}")
        except Exception as e:
             print(f"  ⚠️ Error cancelling orders for {symbol}: {e}")

        try:
            balance = exchange.fetch_balance()
            free_balance = balance.get(coin, {}).get('free', 0.0)
            
            if free_balance > 0:
                safe_amount = float(exchange.amount_to_precision(symbol, free_balance))
                
                if safe_amount > 0:
                    try:
                        order = exchange.create_market_sell_order(symbol, safe_amount)
                        price = order.get('average') or order.get('price') or 'current market'
                        print(f"  🔥 SOLD: {safe_amount} {coin} at {price} price!")
                    except Exception as e:
                        print(f"  ❌ Error selling {coin} (possibly amount < $5 MIN_NOTIONAL): {e}")
                else:
                    print(f"  ℹ️ {coin} balance ({free_balance}) is too small to create a sell order.")
            else:
                print(f"  ℹ️ Free balance for {coin} is empty, nothing to sell.")
        except Exception as e:
             print(f"  ❌ Error checking balance or selling {coin}: {e}")

    print("\n✅ Emergency sell-off procedure completed!")

if __name__ == '__main__':
    main()