import ccxt
import time
import json
import os
from dotenv import load_dotenv
from tg_utils import TelegramManager

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'), override=True)

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
FILE_NAME = os.path.join(current_dir, 'multi_orders.json')

tg = TelegramManager('TG_TOKEN', 'TG_CHAT_ID')
send_telegram = tg.send_message
handle_telegram_commands = tg.handle_commands

# --- CONSERVATOR SETTINGS ---
raw_symbols = os.getenv('CONSERVATOR_SYMBOLS', '').replace(' ', '')
SYMBOLS = raw_symbols.split(',') if raw_symbols else []
TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT_CONSERVATOR', 0))

# Dynamic grid settings (Levels 0 to 10)
GRID_CONFIG = {
    0: {'drop': 0.000, 'pct': 0.025},  # 2.5%
    1: {'drop': 0.005, 'pct': 0.050},  # 5.0%
    2: {'drop': 0.005, 'pct': 0.050},  # 5.0%
    3: {'drop': 0.005, 'pct': 0.050},  # 5.0%
    4: {'drop': 0.010, 'pct': 0.085},  # 8.5%
    5: {'drop': 0.010, 'pct': 0.085},  # 8.5%
    6: {'drop': 0.010, 'pct': 0.085},  # 8.5%
    7: {'drop': 0.015, 'pct': 0.135},  # 13.5%
    8: {'drop': 0.015, 'pct': 0.135},  # 13.5%
    9: {'drop': 0.015, 'pct': 0.135},  # 13.5%
    10: {'drop': 0.020, 'pct': 0.165}, # 16.5%
}

blacklisted_symbols = set() # Store symbols here after exit
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
    """Check: Do taker buys predominate in the last 5-minute candle"""
    try:
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
    keys_to_delete = [k for k, v in active_orders.items() if v['symbol'] == symbol and v.get('side') != 'profit']
    for k in keys_to_delete:
        active_orders.pop(k, None)
    save_orders(active_orders)

def cancel_all_sell_orders(exchange, symbol):
    """Cancels all limit sell orders for a symbol to free up balance"""
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            if order['side'] == 'sell':
                exchange.cancel_order(order['id'], symbol)
                print(f"Cancelled limit sell order {order['id']} for {symbol}")
    except Exception as e:
        print(f"Error cancelling sell orders for {symbol}: {e}")

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
    raw_symbols = os.getenv('CONSERVATOR_SYMBOLS', '').replace(' ', '')
    SYMBOLS = raw_symbols.split(',') if raw_symbols else []
    TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT_CONSERVATOR', 0))

    last_update_id = [0]
    welcome_text = (
        f"🚀 *Conservator (Global DCA Swing) started!*\n"
        f"Symbols: {', '.join(SYMBOLS)}\n\n"
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
            
            raw_symbols = os.getenv('CONSERVATOR_SYMBOLS', '').replace(' ', '')
            SYMBOLS = raw_symbols.split(',') if raw_symbols else []
            TOTAL_BUDGET = float(os.getenv('TOTAL_BUDGET_USDT_CONSERVATOR', 0))
            
            raw_exits = os.getenv('CONSERVATOR_EXIT_SYMBOLS', '').replace(' ', '')
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
            handle_telegram_commands(exchange, active_orders, tickers, None, last_update_id)

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
                        # Activate radar if price drops 1% or cooldown expires
                        if current_price <= c_data['sale_price'] * 0.99 or time.time() >= c_data['expire_time']:
                            del cooldown_data[symbol]
                            send_telegram(f"📡 {symbol}: Radar mode activated! Waiting for buyers market to re-enter.")
                        else:
                            continue

                # --- 1. MARKET ENTRY (NO BASE) ---
                if not positions and not limit_buys:
                    if time.time() < entry_check_timers.get(symbol, 0):
                        continue # Avoid spam, check entry no more than once every 15 sec

                    entry_check_timers[symbol] = time.time() + 15

                    if is_buyers_market(exchange, symbol):
                        base_usdt = TOTAL_BUDGET * GRID_CONFIG[0]['pct']
                        amount_coin = float(exchange.amount_to_precision(symbol, base_usdt / current_price))
                        try:
                            order = exchange.create_market_buy_order(symbol, amount_coin)
                            exec_price = order.get('average') or current_price
                            
                            # Save Base Position
                            pos_id = f"pos_{symbol}_0_{int(time.time())}"
                            active_orders[pos_id] = {
                                'symbol': symbol, 'side': 'position', 'level': 0,
                                'buy_price': exec_price, 'amount': amount_coin
                            }
                            active_orders[f"meta_{symbol}"] = {
                                'symbol': symbol, 'side': 'meta', 'real_avg': exec_price
                            }
                            send_telegram(f"🔥 {symbol}: BASE BOUGHT (Lvl 0) at {exec_price}")
                            
                            # Place limit order for level 1
                            buy_limit_price = exec_price * (1 - GRID_CONFIG[1]['drop'])
                            safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                            so_usdt = TOTAL_BUDGET * GRID_CONFIG[1]['pct']
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

                # --- 2. CHECKING EXECUTION OF SAFETY ORDERS ---
                for oid, l_data in list(limit_buys.items()):
                    try:
                        info = exchange.fetch_order(oid, symbol)
                        if info['status'] == 'closed':
                            lvl = l_data['level']
                            exec_price = l_data['price']
                            
                            # Convert limit order to position
                            pos_id = f"pos_{symbol}_{lvl}_{int(time.time())}"
                            active_orders[pos_id] = {
                                'symbol': symbol, 'side': 'position', 'level': lvl,
                                'buy_price': exec_price, 'amount': l_data['amount']
                            }
                            send_telegram(f"📉 {symbol}: Safety order triggered (Lvl {lvl}) at {exec_price}")
                            del active_orders[oid]
                            
                            # Recalculate and save true average
                            current_positions = [v for v in active_orders.values() if v['symbol'] == symbol and v['side'] == 'position']
                            t_cost = sum(p['buy_price'] * p['amount'] for p in current_positions)
                            t_amount = sum(p['amount'] for p in current_positions)
                            if t_amount > 0:
                                if f"meta_{symbol}" not in active_orders:
                                    active_orders[f"meta_{symbol}"] = {'symbol': symbol, 'side': 'meta'}
                                active_orders[f"meta_{symbol}"]['real_avg'] = t_cost / t_amount
                            
                            # Place next safety order if within standard levels 1-10
                            if lvl < 10:
                                next_lvl = lvl + 1
                                buy_limit_price = exec_price * (1 - GRID_CONFIG[next_lvl]['drop']) # Relative to current level price
                                safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                                so_usdt = TOTAL_BUDGET * GRID_CONFIG[next_lvl]['pct']
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

                # --- 3. GLOBAL TRAILING PROFIT (SELL ALL) ---
                if positions:
                    meta_key = f"meta_{symbol}"
                    meta = active_orders.get(meta_key)
                    
                    if meta and 'real_avg' in meta:
                        avg_price = meta['real_avg']
                    else:
                        t_cost = sum(p['buy_price'] * p['amount'] for p in positions.values())
                        t_amount = sum(p['amount'] for p in positions.values())
                        avg_price = t_cost / t_amount if t_amount > 0 else 0
                        
                        if meta_key not in active_orders:
                            active_orders[meta_key] = {'symbol': symbol, 'side': 'meta'}
                        active_orders[meta_key]['real_avg'] = avg_price
                        save_orders(active_orders)
                        meta = active_orders[meta_key]
                        
                    if 'trailing' not in meta:
                        meta['trailing'] = False
                        meta['high_watermark'] = 0.0
                    
                    if not meta['trailing']:
                        # Target activation: current_price >= avg_price * 1.038
                        if avg_price > 0 and current_price >= avg_price * 1.038:
                            meta['trailing'] = True
                            meta['high_watermark'] = current_price
                            active_orders[meta_key] = meta
                            
                            proj_gross = (current_price - avg_price) * t_amount
                            send_telegram(f"🎯 {symbol}: GLOBAL Trailing activated! Avg Price: {avg_price:.4f}, Current: {current_price:.4f}. Securing profit (~{proj_gross:.2f} USDT)...")
                            save_orders(active_orders)
                    else:
                        hw = meta.get('high_watermark', current_price)
                        if current_price > hw:
                            meta['high_watermark'] = current_price
                            active_orders[meta_key] = meta
                            save_orders(active_orders)
                        else:
                            # Trailing stop: If current_price <= max_price * 0.992 (0.8% callback)
                            sell_threshold = hw * 0.992
                            if current_price <= sell_threshold:
                                try:
                                    # Just to be absolutely sure no locked balance exists
                                    cancel_all_sell_orders(exchange, symbol)
                                    
                                    base_coin = symbol.split('/')[0]
                                    balance = exchange.fetch_free_balance()
                                    coin_balance = balance.get(base_coin, 0)
                                    
                                    amount_to_sell = float(exchange.amount_to_precision(symbol, coin_balance))
                                    if amount_to_sell > 0:
                                        sell_order = exchange.create_market_sell_order(symbol, amount_to_sell)
                                        actual_sell_price = sell_order.get('average') or current_price
                                        
                                        profit_pct = ((actual_sell_price - avg_price) / avg_price) * 100
                                        actual_gross = (actual_sell_price - avg_price) * amount_to_sell
                                        
                                        profit_key = f"profit_{symbol}"
                                        if profit_key not in active_orders:
                                            active_orders[profit_key] = {'symbol': symbol, 'side': 'profit', 'total_usdt': 0.0}
                                        active_orders[profit_key]['total_usdt'] += actual_gross
                                        total_coin_profit = active_orders[profit_key]['total_usdt']
                                        
                                        send_telegram(f"✅ {symbol}: GLOBAL SWING SOLD at {actual_sell_price}!\nTrade Profit: +{profit_pct:.2f}% (💰 {actual_gross:.2f} USDT)\nTotal {symbol} Profit: 🏆 {total_coin_profit:.2f} USDT")
                                    else:
                                        send_telegram(f"⚠️ {symbol}: Tried to global sell but balance was 0!")
                                    
                                    # Clean up entire grid for the symbol
                                    cancel_all_for_symbol(exchange, active_orders, symbol)
                                    
                                    # Enter cooldown
                                    cooldown_data[symbol] = {
                                        'expire_time': time.time() + 300,
                                        'sale_price': actual_sell_price if amount_to_sell > 0 else current_price
                                    }
                                except Exception as e:
                                    print(f"Error selling global {symbol}: {e}")
                                    send_telegram(f"❌ Error during global sell for {symbol}: {e}")

                # --- 4. GRID RESTORATION & CONTINUATION ---
                if positions:
                    max_pos_lvl = max([p['level'] for p in positions.values()])
                    
                    if max_pos_lvl < 10:
                        next_lvl = max_pos_lvl + 1
                        has_next_limit = any(l['level'] == next_lvl for l in limit_buys.values())
                        
                        if not has_next_limit:
                            prev_pos = [p for p in positions.values() if p['level'] == max_pos_lvl][0]
                            prev_buy_price = prev_pos['buy_price']
                            
                            buy_limit_price = prev_buy_price * (1 - GRID_CONFIG[next_lvl]['drop'])
                            safe_price = float(exchange.price_to_precision(symbol, buy_limit_price))
                            
                            so_usdt = TOTAL_BUDGET * GRID_CONFIG[next_lvl]['pct']
                            so_amount = float(exchange.amount_to_precision(symbol, so_usdt / safe_price))
                            
                            try:
                                if current_price > 0:
                                    if current_price <= safe_price:
                                        send_telegram(f"🚨 {symbol}: Price already below missing Lvl {next_lvl} target ({safe_price})! Sending LIMIT order to buy immediately without slippage.")
                                    else:
                                        send_telegram(f"⚠️ {symbol}: Setting missing Limit for Lvl {next_lvl} at {safe_price}.")
                                        
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