import ccxt
import time
import json
import os
import requests
from dotenv import load_dotenv
from tg_utils import TelegramManager

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'), override=True)

API_KEY = os.getenv('AGGRESSOR_API_KEY')
SECRET_KEY = os.getenv('AGGRESSOR_SECRET_KEY')
FILE_NAME = os.path.join(current_dir, 'aggressor_orders.json')

tg = TelegramManager('AGGRESSOR_TG_TOKEN', 'AGGRESSOR_TG_CHAT_ID')
send_telegram = tg.send_message
handle_telegram_commands = tg.handle_commands

# --- AGGRESSOR SETTINGS ---
raw_symbols = os.getenv('AGGRESSOR_SYMBOLS', '').replace(' ', '')
SYMBOLS = raw_symbols.split(',') if raw_symbols else []
TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT', 0))

BASE_PCT = 0.20  # 20% for the first entry (level 0)
SAFETY_PCT = 0.10 # 10% for each safety order (levels 1-8)

# 8 levels: Scalp micro-jumps early on, hold the heavy drops later
DROP_STEPS = [0.009, 0.009, 0.012, 0.015, 0.019, 0.025, 0.030, 0.035]

# Trailing settings are determined dynamically in the loop based on level
# Level 0: 1.5% trigger, 0.4% callback. Levels 1-4: 1.0% trigger, 0.3% callback.
STOP_LOSS = 0.10        # -10% from Base price (full exit)

blacklisted_symbols = set() # Store symbols here after Stop-Loss
cooldown_data = {} # symbol -> {'expire_time': timestamp, 'sale_price': price}
entry_check_timers = {} # symbol -> timestamp (15 sec entry check delay)

def save_orders(orders):
    with open(FILE_NAME, 'w') as f:
        json.dump(orders, f)

def load_orders():
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, 'r') as f:
            return json.load(f)
    return {}

def is_buyers_market(exchange, symbol):
    """Check: Do buys predominate in the last 5-minute candle"""
    try:
        # ccxt format for binance public klines to get taker volume
        market_id = exchange.market(symbol)['id']
        res = exchange.publicGetKlines({'symbol': market_id, 'interval': '5m', 'limit': 1})
        if res and len(res) > 0:
            total_vol = float(res[0][5])
            buy_vol = float(res[0][9]) # Taker buy base asset volume
            sell_vol = total_vol - buy_vol
            return buy_vol > sell_vol
    except Exception as e:
        print(f"Volume check error for {symbol}: {e}")
    return False

def cancel_all_for_symbol(exchange, active_orders, symbol):
    """Cancels all limit orders and clears memory for the symbol"""
    try:
        exchange.cancel_all_orders(symbol)
    except Exception:
        pass
    keys_to_delete = [k for k, v in active_orders.items() if v['symbol'] == symbol]
    for k in keys_to_delete:
        active_orders.pop(k, None)
    save_orders(active_orders)

def main():
    global SYMBOLS, TOTAL_BUDGET
    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'enableRateLimit': True,
        'options': {
            'adjustForTimeDifference': True,
            'recvWindow': 10000
        }
    })
    
    # Sync local time with Binance server time to avoid timestamp errors
    exchange.load_time_difference()
    
    exchange.load_markets()
    active_orders = load_orders()

    # Re-read config one more time before starting to ensure we are using latest .env values
    raw_symbols = os.getenv('AGGRESSOR_SYMBOLS', '').replace(' ', '')
    SYMBOLS = raw_symbols.split(',') if raw_symbols else []
    TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT', 0))

    last_update_id = [0]
    welcome_text = (
        f"🚀 *Aggressor (Cascade) started!*\n"
        f"Symbols: {', '.join(SYMBOLS)} | Budget: {TOTAL_BUDGET}$\n\n"
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
    send_telegram(welcome_text, reply_markup=keyboard)

    while True:
        try:
            # Hot reload .env and config variables without stopping the bot
            load_dotenv(os.path.join(current_dir, '.env'), override=True)
            
            raw_symbols = os.getenv('AGGRESSOR_SYMBOLS', '').replace(' ', '')
            SYMBOLS = raw_symbols.split(',') if raw_symbols else []
            TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT', 0))
            
            raw_exits = os.getenv('AGGRESSOR_EXIT_SYMBOLS', '').replace(' ', '')
            EXIT_SYMBOLS = raw_exits.split(',') if raw_exits else []
            
            # EMERGENCY EXIT LOGIC
            for ex_sym in EXIT_SYMBOLS:
                if ex_sym in blacklisted_symbols:
                    continue
                
                send_telegram(f"⚠️ {ex_sym}: Coin moved to EXIT list. Selling positions and cancelling orders!")
                
                # 1. Cancel all limit orders and clear memory FIRST
                cancel_all_for_symbol(exchange, active_orders, ex_sym)
                
                # 2. Sell ALL available balance of the coin directly from the exchange
                base_coin = ex_sym.split('/')[0]
                try:
                    balance = exchange.fetch_free_balance()
                    coin_balance = balance.get(base_coin, 0)
                    
                    if coin_balance > 0:
                        amount_to_sell = float(exchange.amount_to_precision(ex_sym, coin_balance))
                        if amount_to_sell > 0:
                            exchange.create_market_sell_order(ex_sym, amount_to_sell)
                            send_telegram(f"✅ {ex_sym}: Emergency market sell completed ({amount_to_sell} {base_coin}).")
                        else:
                            send_telegram(f"ℹ️ {ex_sym}: Balance too small to sell ({coin_balance} {base_coin}).")
                    else:
                        send_telegram(f"ℹ️ {ex_sym}: No balance found on exchange to sell.")
                except Exception as e:
                    print(f"Error emergency selling {ex_sym}: {e}")
                    send_telegram(f"❌ {ex_sym}: Sell failed! Error: {e}")
                
                # Blacklist the coin in case it is mistakenly left in SYMBOLS
                blacklisted_symbols.add(ex_sym)

            try:
                if not SYMBOLS:
                    time.sleep(5)
                    continue
                tickers = exchange.fetch_tickers(SYMBOLS)
            except Exception:
                time.sleep(5)
                continue

            # Handle Telegram commands without blocking the loop
            handle_telegram_commands(active_orders, tickers, DROP_STEPS, last_update_id)

            for symbol in SYMBOLS:
                if symbol in blacklisted_symbols:
                    continue
                
                symbol_data = {k: v for k, v in active_orders.items() if v['symbol'] == symbol}
                positions = {k: v for k, v in symbol_data.items() if v['side'] == 'position'}
                limit_buys = {k: v for k, v in symbol_data.items() if v['side'] == 'buy'}
                current_price = tickers[symbol]['last'] if symbol in tickers else 0
                
                if symbol in cooldown_data:
                    c_data = cooldown_data[symbol]
                    if current_price > 0:
                        if current_price <= c_data['sale_price'] * 0.99 or time.time() >= c_data['expire_time']:
                            del cooldown_data[symbol]
                            send_telegram(f"📡 {symbol}: Radar mode activated! Waiting for buyers market to re-enter.")
                        else:
                            continue

                # --- 1. EMERGENCY STOP-LOSS (-10%) ---
                if positions and current_price > 0:
                    total_cost = sum(p['buy_price'] * p['amount'] for p in positions.values())
                    total_amount = sum(p['amount'] for p in positions.values())
                    avg_price = total_cost / total_amount if total_amount > 0 else 0
                    
                    if avg_price > 0 and current_price <= avg_price * (1 - STOP_LOSS):
                        send_telegram(f"⛔️ PANIC! {symbol} dropped by 10% from average price. Selling everything at market price!")
                        
                        # 1. Cancel all limit orders and clear memory FIRST
                        cancel_all_for_symbol(exchange, active_orders, symbol)
                        
                        # 2. Sell ALL available balance directly from the exchange
                        base_coin = symbol.split('/')[0]
                        try:
                            balance = exchange.fetch_free_balance()
                            coin_balance = balance.get(base_coin, 0)
                            
                            if coin_balance > 0:
                                amount_to_sell = float(exchange.amount_to_precision(symbol, coin_balance))
                                if amount_to_sell > 0:
                                    exchange.create_market_sell_order(symbol, amount_to_sell)
                                    send_telegram(f"✅ {symbol}: Stop-Loss market sell completed ({amount_to_sell} {base_coin}).")
                                else:
                                    send_telegram(f"ℹ️ {symbol}: Balance too small to sell ({coin_balance} {base_coin}).")
                            else:
                                send_telegram(f"ℹ️ {symbol}: No balance found on exchange to sell.")
                        except Exception as e:
                            print(f"Error Stop-Loss selling {symbol}: {e}")
                            send_telegram(f"❌ {symbol}: Stop-Loss sell failed! Error: {e}")
                            
                        blacklisted_symbols.add(symbol)
                        send_telegram(f"🛑 Trading for {symbol} has been fully stopped.")
                        continue

                # --- 2. MARKET ENTRY (NO BASE) ---
                if not positions and not limit_buys:
                    if time.time() < entry_check_timers.get(symbol, 0):
                        continue # Avoid spam, check entry no more than once every 15 sec

                    entry_check_timers[symbol] = time.time() + 15

                    if is_buyers_market(exchange, symbol):
                        base_usdt = TOTAL_BUDGET * BASE_PCT
                        amount_coin = float(exchange.amount_to_precision(symbol, base_usdt / current_price))
                        try:
                            order = exchange.create_market_buy_order(symbol, amount_coin)
                            exec_price = order.get('average') or current_price
                            
                            # Save Base
                            pos_id = f"pos_{symbol}_0_{int(time.time())}"
                            active_orders[pos_id] = {
                                'symbol': symbol, 'side': 'position', 'level': 0,
                                'buy_price': exec_price, 'amount': amount_coin,
                                'trailing': False, 'high_watermark': exec_price
                            }
                            send_telegram(f"🔥 {symbol}: BASE BOUGHT (Lvl 0) at {exec_price}")
                            
                            # Place limit order for level 1
                            buy_limit_price = exec_price * (1 - DROP_STEPS[0])
                            safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                            so_usdt = TOTAL_BUDGET * SAFETY_PCT
                            so_amount = float(exchange.amount_to_precision(symbol, so_usdt / safe_price))
                            
                            l_order = exchange.create_limit_buy_order(symbol, so_amount, safe_price)
                            active_orders[l_order['id']] = {
                                'symbol': symbol, 'side': 'buy', 'level': 1,
                                'price': safe_price, 'amount': so_amount
                            }
                            save_orders(active_orders)
                        except Exception as e:
                            print(f"Error buying base {symbol}: {e}")
                    continue

                # --- 3. CHECKING EXECUTION OF LIMIT ORDERS (LEVELS 1-4) ---
                for oid, l_data in list(limit_buys.items()):
                    try:
                        info = exchange.fetch_order(oid, symbol)
                        if info['status'] == 'closed':
                            lvl = l_data['level']
                            exec_price = l_data['price']
                            
                            # Turn limit order into position
                            pos_id = f"pos_{symbol}_{lvl}_{int(time.time())}"
                            active_orders[pos_id] = {
                                'symbol': symbol, 'side': 'position', 'level': lvl,
                                'buy_price': exec_price, 'amount': l_data['amount'],
                                'trailing': False, 'high_watermark': exec_price
                            }
                            send_telegram(f"📉 {symbol}: Safety order triggered (Lvl {lvl}) at {exec_price}")
                            del active_orders[oid]
                            
                            # Place next safety order (if exists)
                            if lvl < 8:
                                next_lvl = lvl + 1
                                buy_limit_price = exec_price * (1 - DROP_STEPS[lvl]) # Step from current price
                                safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                                so_usdt = TOTAL_BUDGET * SAFETY_PCT
                                so_amount = float(exchange.amount_to_precision(symbol, so_usdt / safe_price))
                                
                                new_order = exchange.create_limit_buy_order(symbol, so_amount, safe_price)
                                active_orders[new_order['id']] = {
                                    'symbol': symbol, 'side': 'buy', 'level': next_lvl,
                                    'price': safe_price, 'amount': so_amount
                                }
                            save_orders(active_orders)
                    except ccxt.OrderNotFound as e:
                        print(f"Order {oid} for {symbol} not found on exchange. Cleaning up local tracker.")
                        del active_orders[oid]
                        save_orders(active_orders)
                    except ccxt.NetworkError:
                        pass
                    except ccxt.InvalidNonce:
                        exchange.load_time_difference()
                    except Exception as e:
                        print(f"Error checking limit order {symbol}: {e}")

                # --- 4. INDEPENDENT TRAILING PROFIT (SELL) ---
                for pid, p_data in list({k:v for k,v in active_orders.items() if v['side'] == 'position' and v['symbol'] == symbol}.items()):
                    b_price = p_data['buy_price']
                    lvl = p_data['level']
                    
                    trigger_pct = 0.0195 if lvl == 0 else 0.0095
                    callback_pct = 0.005 if lvl == 0 else 0.003
                    floor_pct = trigger_pct - 0.0005
                    
                    if not p_data['trailing']:
                        # Enable trailing
                        if current_price >= b_price * (1 + trigger_pct):
                            p_data['trailing'] = True
                            p_data['high_watermark'] = current_price
                            send_telegram(f"🎯 {symbol}: Trailing activated for (Lvl {lvl}). Minimum profit secured: {floor_pct*100}%!")
                            save_orders(active_orders)
                    else:
                        hw = p_data['high_watermark']
                        if current_price > hw:
                            p_data['high_watermark'] = current_price
                            save_orders(active_orders)
                        else:
                            sell_threshold = max(hw * (1 - callback_pct), b_price * (1 + floor_pct))
                            if current_price <= sell_threshold:
                                # SELL!
                                try:
                                    sell_order = exchange.create_market_sell_order(symbol, p_data['amount'])
                                    actual_sell_price = sell_order.get('average') or current_price
                                    profit_pct = ((actual_sell_price - b_price) / b_price) * 100
                                    send_telegram(f"✅ {symbol}: SOLD (Lvl {lvl}) at {actual_sell_price}!\nProfit: +{profit_pct:.2f}%")
                                
                                    del active_orders[pid]
                                
                                    # CASCADE LOGIC
                                    if lvl == 0:
                                        # Sold base -> cancel all limit orders and wait for new base
                                        cancel_all_for_symbol(exchange, active_orders, symbol)
                                        send_telegram(f"♻️ {symbol}: Base sold. Grid reset, waiting for new entry.")
                                        send_telegram("⏳ Waiting for 1% drop OR 5 minutes (market cooling)...")
                                        cooldown_data[symbol] = {
                                            'expire_time': time.time() + 300,
                                            'sale_price': actual_sell_price
                                        }
                                    else:
                                        # Sold level N -> cancel limit order N+1 and place limit order N dynamically from actual sale price
                                        next_lvl = lvl + 1
                                        # Find and cancel order N+1
                                        for oid, l_data in list(active_orders.items()):
                                            if l_data['symbol'] == symbol and l_data['side'] == 'buy' and l_data['level'] == next_lvl:
                                                try:
                                                    exchange.cancel_order(oid, symbol)
                                                    del active_orders[oid]
                                                except: pass
                                    
                                        # Returning entry for the sold level N dynamically
                                        step_index = lvl - 1 if lvl > 0 else 0
                                    
                                        # Ensure we don't overlap grids by putting the grid above the previous level
                                        prev_lvl_buy_price = None
                                        for oid, v in list(active_orders.items()):
                                            if v['symbol'] == symbol and v['side'] == 'position' and v['level'] == lvl - 1:
                                                prev_lvl_buy_price = v['buy_price']
                                                break
                                    
                                        reference_price = actual_sell_price
                                        if prev_lvl_buy_price is not None:
                                            reference_price = min(actual_sell_price, prev_lvl_buy_price)

                                        buy_limit_price = reference_price * (1 - DROP_STEPS[step_index])
                                        safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                                    
                                        so_usdt = TOTAL_BUDGET * SAFETY_PCT
                                        so_amount = float(exchange.amount_to_precision(symbol, so_usdt / safe_price))
                                        new_order = exchange.create_limit_buy_order(symbol, so_amount, safe_price)
                                        active_orders[new_order['id']] = {
                                            'symbol': symbol, 'side': 'buy', 'level': lvl,
                                            'price': safe_price, 'amount': so_amount
                                        }
                                        send_telegram(f"🔄 {symbol}: Re-placed entry for (Lvl {lvl}) at {safe_price} (from sale at {actual_sell_price}).")
                                        save_orders(active_orders)

                                except Exception as e:
                                    print(f"Error selling {symbol}: {e}")

                # --- 5. GRID RESTORATION ---
                if positions:
                    max_pos_lvl = max([p['level'] for p in positions.values()])
                    if max_pos_lvl < 8:
                        next_lvl = max_pos_lvl + 1
                        has_next_limit = any(l['level'] == next_lvl for l in limit_buys.values())
                        
                        if not has_next_limit:
                            prev_pos = [p for p in positions.values() if p['level'] == max_pos_lvl][0]
                            prev_buy_price = prev_pos['buy_price']
                            
                            step_index = max_pos_lvl
                            buy_limit_price = prev_buy_price * (1 - DROP_STEPS[step_index])
                            safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                            
                            so_usdt = TOTAL_BUDGET * SAFETY_PCT
                            so_amount = float(exchange.amount_to_precision(symbol, so_usdt / safe_price))
                            
                            try:
                                if current_price > 0:
                                    if current_price <= safe_price:
                                        send_telegram(f"🚨 {symbol}: Price already below missing Lvl {next_lvl} target ({safe_price})! Sending LIMIT order to buy immediately without slippage.")
                                    else:
                                        send_telegram(f"⚠️ {symbol}: Hole in the grid detected. Setting missing Limit for Lvl {next_lvl} at {safe_price}.")
                                        
                                    new_order = exchange.create_limit_buy_order(symbol, so_amount, safe_price)
                                    active_orders[new_order['id']] = {
                                        'symbol': symbol, 'side': 'buy', 'level': next_lvl,
                                        'price': safe_price, 'amount': so_amount
                                    }
                                    save_orders(active_orders)
                            except Exception as e:
                                print(f"Error restoring limit order {symbol}: {e}")

            time.sleep(2)

        except Exception as e:
            print(f"General Error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()