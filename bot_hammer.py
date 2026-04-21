import os
import asyncio
import ccxt.pro as ccxtpro
import json
from dotenv import load_dotenv, set_key
from tg_utils import TelegramManager

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'), override=True)

API_KEY = os.getenv('HAMMER_API_KEY')
SECRET_KEY = os.getenv('HAMMER_SECRET_KEY')
# Configurable budget in .env (defaults to 100 USDT)
BUDGET = float(os.getenv('HAMMER_BUDGET_USDT', 100))
MAX_CONCURRENT_TRADES = 3
SIGNALS_FILE = os.path.join(current_dir, 'hammer_signals.txt')
PROFIT_FILE = os.path.join(current_dir, 'hammer_profit.json')

tg = TelegramManager('HAMMER_TG_TOKEN', 'HAMMER_TG_CHAT_ID')

active_tasks = {}
consecutive_losses = 0
accepting_signals = True

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
    global consecutive_losses, accepting_signals, total_hammer_profit
    
    max_price = buy_price
    # Base Stop-Loss: -0.80%
    stop_trigger = buy_price * (1 - 0.008) 
    
    tg.send_message(f"🔨 *BOUGHT* {symbol}\nEntry: {buy_price}\nAmount: {amount}\nInitial Stop: {stop_trigger:.4f} (-0.80%)")
    print(f"✅ [ENTER] {symbol} | Buy Price: {buy_price} | Amount: {amount}")
    
    hard_stop_id = None
    try:
        # Place a "hard" emergency stop-loss on the exchange (-2.0%)
        stop_price = float(exchange.price_to_precision(symbol, buy_price * 0.980))
        limit_price = float(exchange.price_to_precision(symbol, buy_price * 0.975)) 
        
        hard_stop_order = await exchange.create_order(
            symbol, 'STOP_LOSS_LIMIT', 'sell', amount, limit_price, {'stopPrice': stop_price}
        )
        hard_stop_id = hard_stop_order['id']
        print(f"🛡️ [{symbol}] Emergency hard stop-loss placed on the exchange ({stop_price})")
    except Exception as e:
        print(f"⚠️ [{symbol}] Failed to place emergency stop-loss: {e}")

    while True:
        try:
            # Async WebSocket stream
            ticker = await exchange.watch_ticker(symbol)
            current_price = float(ticker['last'])
            
            # Track maximum price
            if current_price > max_price:
                max_price = current_price
            
            profit_pct = (current_price - buy_price) / buy_price
            
            # ------------------------------------------------
            # STEP TRAILING (Step: 0.50%)
            # +0.50% -> stop at 0 (breakeven)
            # +1.00% -> stop at +0.50% and so on
            # ------------------------------------------------
            if profit_pct >= 0.005:
                steps_achieved = int(profit_pct // 0.005)
                dynamic_stop_pct = (steps_achieved - 1) * 0.005
                new_stop = buy_price * (1 + dynamic_stop_pct)
                
                # Stop-trigger moves only upwards
                if new_stop > stop_trigger:
                    stop_trigger = new_stop
                    tg.send_message(f"📈 *TRAILING* {symbol}\nProfit reached: +{profit_pct*100:.2f}%\nMoved Stop to: +{dynamic_stop_pct*100:.2f}% ({stop_trigger:.4f})")
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
                        await asyncio.sleep(0.5) # Give Binance time to unlock the balance!
                    except Exception as e:
                        print(f"[{symbol}] Error cancelling emergency stop: {e}")
                        
                sold = False
                for attempt in range(3):
                    try:
                        sell_order = await exchange.create_market_sell_order(symbol, amount)
                        sell_price = float(sell_order.get('average') or current_price)
                        sold = True
                        break
                    except Exception as e:
                        print(f"[{symbol}] Sell execution error (Attempt {attempt+1}/3): {e}")
                        await asyncio.sleep(1)
                        
                if not sold:
                    tg.send_message(f"🚨 *CRITICAL ERROR: {symbol}* 🚨\nBot failed to market sell after 3 attempts! The coin is stuck on your balance.")
                    break # Exit tracking without recording fake profit
                    
                # Calculate Gross and Net PnL (assuming 0.075% fee per side with BNB = 0.15% round-trip)
                gross_pnl_usdt = (sell_price - buy_price) * amount
                total_fee_usdt = (buy_price * amount * 0.00075) + (sell_price * amount * 0.00075)
                pnl_usdt = gross_pnl_usdt - total_fee_usdt
                
                final_profit_pct = (pnl_usdt / (buy_price * amount)) * 100
                
                total_hammer_profit += pnl_usdt
                save_profit(total_hammer_profit)
                
                # Track consecutive losses
                if final_profit_pct < 0:
                    consecutive_losses += 1
                    icon = "❌"
                else:
                    consecutive_losses = 0
                    icon = "✅"
                    
                tg.send_message(f"{icon} *SOLD* {symbol}\nExit: {sell_price}\nProfit: {final_profit_pct:.2f}% (💰 {pnl_usdt:.2f} USDT)\nLosses in a row: {consecutive_losses}\n\n🏆 *Total Bot Profit:* {total_hammer_profit:.2f} USDT")
                
                # Daily Stop-Loss
                if consecutive_losses >= 3 and accepting_signals:
                    accepting_signals = False
                    
                    # Tell the scanner to stop as well by updating .env
                    try:
                        set_key(os.path.join(current_dir, '.env'), 'HAMMER_STATUS', 'STOP')
                    except Exception as e:
                        print(f"Failed to update .env: {e}")
                        
                    tg.send_message("🛑 *FATAL STOP*\nHit 3 consecutive stop-losses. Stopping new entries, but finishing active trades!")
                    print("Hit 3 losses. Stopping new entries and setting HAMMER_STATUS=STOP in .env.")
                    
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
    global accepting_signals, total_hammer_profit
    exchange = ccxtpro.binance({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    await exchange.load_markets()
    
    # Clear signals file on startup
    open(SIGNALS_FILE, 'w').close() 
    
    welcome_text = (
        f"🔨 *Bot Started*\n"
        f"Budget: {BUDGET} USDT\n"
        f"Total Historical Profit: {total_hammer_profit:.2f} USDT\n\n"
        f"If this tool helps you earn, please consider supporting further development and rigorous testing. Every bit helps!\n\n"
        f"USDT (BEP20): `0x213d642eca4cb68731e61a6e4716deb5882c4364`\n"
        f"Binance ID: `498092588`\n"
        f"_(Tap to copy)_"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "💳 Open Binance Pay", "url": "https://www.binance.com/en/my/payment/send"}
        ]]
    }
    tg.send_message(welcome_text, reply_markup=keyboard)
    print(f"Hammer running. Total Historical Profit: {total_hammer_profit:.2f} USDT. Waiting for signals...")
    
    while accepting_signals:
        try:
            # Hot reload .env to check for manual stop
            load_dotenv(os.path.join(current_dir, '.env'), override=True)
            if os.getenv('HAMMER_STATUS', 'RUNNING').upper() == 'STOP':
                accepting_signals = False
                tg.send_message("🛑 *MANUAL STOP*\nDetected 'STOP' in .env. Stopping new entries, finishing active trades!")
                print("Manual STOP detected in .env. Stopping new entries.")
                break
                
            if os.path.exists(SIGNALS_FILE):
                with open(SIGNALS_FILE, 'r') as f:
                    lines = f.readlines()
                
                if lines:
                    open(SIGNALS_FILE, 'w').close() 
                    
                    for line in lines:
                        symbol = line.strip()
                        if symbol and symbol not in active_tasks:
                            if len(active_tasks) >= MAX_CONCURRENT_TRADES:
                                print(f"Max trades ({MAX_CONCURRENT_TRADES}) reached. Ignoring signal for {symbol}.")
                                continue
                                
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
            
    # Wait for remaining positions to close naturally
    if active_tasks:
        print("Waiting for remaining positions to close...")
        tg.send_message("⏳ *INFO*\nFatal stop triggered, but keeping connection alive to manage remaining open positions...")
        while active_tasks:
            await asyncio.sleep(1)
            
    await exchange.close()
    tg.send_message("🛑 *SHUTDOWN COMPLETE*\nAll positions closed. Bot is offline.")
    print("Hammer shutdown complete.")

if __name__ == '__main__':
    asyncio.run(main())