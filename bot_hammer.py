import os
import asyncio
import ccxt.pro as ccxtpro
import json
from dotenv import load_dotenv
from tg_utils import TelegramManager

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'), override=True)

API_KEY = os.getenv('HAMMER_API_KEY')
SECRET_KEY = os.getenv('HAMMER_SECRET_KEY')
# Configurable budget in .env (defaults to 100 USDT)
BUDGET = float(os.getenv('HAMMER_BUDGET_USDT', 100))
SIGNALS_FILE = os.path.join(current_dir, 'hammer_signals.txt')
PROFIT_FILE = os.path.join(current_dir, 'hammer_profit.json')

tg = TelegramManager('HAMMER_TG_TOKEN', 'HAMMER_TG_CHAT_ID')

active_tasks = {}
consecutive_losses = 0
bot_active = True

def load_profit():
    if os.path.exists(PROFIT_FILE):
        with open(PROFIT_FILE, 'r') as f:
            return json.load(f).get('total_profit', 0.0)
    return 0.0

def save_profit(profit):
    with open(PROFIT_FILE, 'w') as f:
        json.dump({'total_profit': profit}, f)

total_hammer_profit = load_profit()

async def manage_position(exchange, symbol, buy_price, amount):
    """Tracks the position via WebSockets and executes dynamic step trailing."""
    global consecutive_losses, bot_active, total_hammer_profit
    
    max_price = buy_price
    # Base Stop-Loss: -0.22%
    stop_trigger = buy_price * (1 - 0.0022) 
    
    tg.send_message(f"🔨 *HAMMER BOUGHT* {symbol}\nEntry: {buy_price}\nAmount: {amount}\nInitial Stop: {stop_trigger:.4f} (-0.22%)")
    print(f"✅ [ENTER] {symbol} | Buy Price: {buy_price} | Amount: {amount}")
    
    hard_stop_id = None
    try:
        # Place a "hard" emergency stop-loss on the exchange in case the bot freezes (-1.5%)
        stop_price = float(exchange.price_to_precision(symbol, buy_price * 0.985))
        limit_price = float(exchange.price_to_precision(symbol, buy_price * 0.980)) # Limit price slightly lower to guarantee execution
        
        hard_stop_order = await exchange.create_order(
            symbol, 'STOP_LOSS_LIMIT', 'sell', amount, limit_price, {'stopPrice': stop_price}
        )
        hard_stop_id = hard_stop_order['id']
        print(f"🛡️ [{symbol}] Emergency hard stop-loss placed on the exchange ({stop_price})")
    except Exception as e:
        print(f"⚠️ [{symbol}] Failed to place emergency stop-loss: {e}")

    while bot_active:
        try:
            # Async WebSocket stream
            ticker = await exchange.watch_ticker(symbol)
            current_price = float(ticker['last'])
            
            # Track maximum price
            if current_price > max_price:
                max_price = current_price
            
            profit_pct = (current_price - buy_price) / buy_price
            
            # ------------------------------------------------
            # STEP TRAILING (Step: 0.22%)
            # +0.22% -> stop at 0 (breakeven)
            # +0.44% -> stop at +0.22% and so on
            # ------------------------------------------------
            if profit_pct >= 0.0022:
                steps_achieved = int(profit_pct // 0.0022)
                dynamic_stop_pct = (steps_achieved - 1) * 0.0022
                new_stop = buy_price * (1 + dynamic_stop_pct)
                
                # Stop-trigger moves only upwards
                if new_stop > stop_trigger:
                    stop_trigger = new_stop
                    tg.send_message(f"📈 *HAMMER TRAILING* {symbol}\nProfit reached: +{profit_pct*100:.2f}%\nMoved Stop to: +{dynamic_stop_pct*100:.2f}% ({stop_trigger:.4f})")
                    print(f"[{symbol}] Trailing stop updated to {stop_trigger}")
            
            # ------------------------------------------------
            # EXIT POSITION (100% Market Sell)
            # ------------------------------------------------
            if current_price <= stop_trigger:
                print(f"⚠️ [{symbol}] EXIT TRIGGERED at {current_price}! Executing Market Sell...")
                
                # Cancel the hard stop order to unlock the balance before the market sell
                if hard_stop_id:
                    try:
                        await exchange.cancel_order(hard_stop_id, symbol)
                    except Exception as e:
                        print(f"[{symbol}] Error cancelling emergency stop: {e}")
                        
                try:
                    sell_order = await exchange.create_market_sell_order(symbol, amount)
                    sell_price = float(sell_order.get('average') or current_price)
                except Exception as e:
                    print(f"[{symbol}] Sell execution error: {e}")
                    sell_price = current_price # Fallback for reporting
                    
                final_profit_pct = ((sell_price - buy_price) / buy_price) * 100
                pnl_usdt = (sell_price - buy_price) * amount
                
                total_hammer_profit += pnl_usdt
                save_profit(total_hammer_profit)
                
                # Track consecutive losses
                if final_profit_pct < 0:
                    consecutive_losses += 1
                    icon = "❌"
                else:
                    consecutive_losses = 0
                    icon = "✅"
                    
                print(f"🛑 [EXIT] {symbol} | Sell Price: {sell_price} | PNL: {pnl_usdt:.2f} USDT | Bot Total Profit: {total_hammer_profit:.2f} USDT")
                tg.send_message(f"{icon} *HAMMER SOLD* {symbol}\nExit: {sell_price}\nProfit: {final_profit_pct:.2f}% (💰 {pnl_usdt:.2f} USDT)\nLosses in a row: {consecutive_losses}\n\n🏆 *Total Bot Profit:* {total_hammer_profit:.2f} USDT")
                
                # Daily Stop-Loss
                if consecutive_losses >= 3:
                    bot_active = False
                    tg.send_message("🛑 *HAMMER FATAL STOP*\nHit 3 consecutive stop-losses. Market is too choppy. Shutting down!")
                    print("Hit 3 losses. Stopping bot.")
                    
                break
                
        except ccxtpro.NetworkError:
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[{symbol}] WS Error: {e}")
            await asyncio.sleep(1)
            
    # Cleanup task
    if symbol in active_tasks:
        del active_tasks[symbol]

async def main():
    global bot_active, total_hammer_profit
    exchange = ccxtpro.binance({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    await exchange.load_markets()
    
    # Clear signals file on startup
    open(SIGNALS_FILE, 'w').close() 
    
    msg = f"🔨 *Hammer Bot Started*\nBudget: {BUDGET} USDT\nTotal Historical Profit: {total_hammer_profit:.2f} USDT\nWaiting for scanner signals..."
    tg.send_message(msg)
    print(f"Hammer running. Total Historical Profit: {total_hammer_profit:.2f} USDT. Waiting for signals...")
    
    while bot_active:
        try:
            if os.path.exists(SIGNALS_FILE):
                with open(SIGNALS_FILE, 'r') as f:
                    lines = f.readlines()
                
                if lines:
                    open(SIGNALS_FILE, 'w').close() 
                    
                    for line in lines:
                        symbol = line.strip()
                        if symbol and symbol not in active_tasks:
                            print(f"Signal received for {symbol}! Entering market...")
                            try:
                                ticker = await exchange.fetch_ticker(symbol)
                                cur_price = float(ticker['last'])
                                amount_coin = float(exchange.amount_to_precision(symbol, BUDGET / cur_price))
                                
                                order = await exchange.create_market_buy_order(symbol, amount_coin)
                                exec_price = float(order.get('average') or cur_price)
                                
                                task = asyncio.create_task(manage_position(exchange, symbol, exec_price, amount_coin))
                                active_tasks[symbol] = task
                            except Exception as e:
                                print(f"Error executing buy for {symbol}: {e}")
            
            await asyncio.sleep(0.5) 
            
        except Exception as e:
            print(f"Main loop error: {e}")
            await asyncio.sleep(2)
            
    await exchange.close()

if __name__ == '__main__':
    asyncio.run(main())