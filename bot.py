import ccxt
import time
import json
import os
import requests
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(current_dir, '.env'))

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
FILE_NAME = os.path.join(current_dir, 'multi_orders.json')
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"TG Error: {e}")

def get_status_report(exchange, active_orders):
    try:
        balance = exchange.fetch_balance()
        usdt_free = balance['free'].get('USDT', 0)
        
        report = "📊 **COIN REPORT**\n\n"
        
        grouped = {}
        for oid, data in active_orders.items():
            sym = data['symbol']
            if sym not in grouped: grouped[sym] = []
            grouped[sym].append(data)
            
        for symbol in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']:
            icon = "🧡" if "BTC" in symbol else "💎" if "ETH" in symbol else "💜"
            orders = grouped.get(symbol, [])
            
            # Count buy orders and positions
            buys = [o for o in orders if o['side'] == 'buy']
            sells = [o for o in orders if o['side'] == 'position']
            
            report += f"{icon} **{symbol}**\n"
            report += f"   • BUY Orders: {len(buys)}\n"
            report += f"   • Positions: {len(sells)}\n"
            
            if sells:
                avg_price = sum([o.get('buy_price', o.get('price', 0)) for o in sells]) / len(sells)
                report += f"   • In Position (Avg Entry): {avg_price:.2f}\n"
            else:
                report += f"   • In Position: No\n"
            report += "\n"
            
        report += f"💵 **Free Balance:** {usdt_free:.2f} USDT"
        return report
    except Exception as e:
        return f"❌ Failed to generate report: {e}"

def save_orders(orders):
    with open(FILE_NAME, 'w') as f:
        json.dump(orders, f)

def load_orders():
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, 'r') as f:
            return json.load(f)
    return {}

def main():
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
    exchange.load_markets()

    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'] 
    step_percent = 0.005 
    step_multipliers = [1, 2, 3]
    levels = 3           
    trade_amount_usdt = 88.0 
    activation_base = 0.011
    trailing_base = 0.004
    activation_safety = 0.007
    trailing_safety = 0.002
    
    active_orders = load_orders()

    try:
        symbols_in_memory = {data['symbol'] for data in active_orders.values()}
        symbols_to_setup = [s for s in SYMBOLS if s not in symbols_in_memory]

        if symbols_to_setup:
            print(f"🧹 Found new/incomplete coins to setup: {', '.join(symbols_to_setup)}")
            for symbol in symbols_to_setup:
                try:
                    print(f"\n🏗️ Cancelling old orders and building grid for {symbol}...")
                    try:
                        exchange.cancel_all_orders(symbol)
                    except Exception:
                        pass
                    time.sleep(1)

                    current_price = exchange.fetch_ticker(symbol)['last']
                    amount_coin = trade_amount_usdt / current_price
                    safe_amount = float(exchange.amount_to_precision(symbol, amount_coin))
                    
                    market_order = exchange.create_market_buy_order(symbol, safe_amount)
                    executed_price = market_order.get('average') or market_order.get('price') or current_price
                    
                    time.sleep(2) 
                    base_coin = symbol.split('/')[0]
                    balance = exchange.fetch_balance()
                    free_balance = balance.get(base_coin, {}).get('free', 0.0)
                    
                    sell_amount = float(exchange.amount_to_precision(symbol, min(safe_amount, free_balance)))
                    
                    if sell_amount <= 0:
                        raise Exception(f"Failed to fetch bought balance for {base_coin} after market buy.")

                    pos_id = f"pos_{symbol}_{int(time.time()*1000)}_0"
                    active_orders[pos_id] = {
                        'symbol': symbol, 
                        'side': 'position', 
                        'buy_price': executed_price, 
                        'level': 0, 
                        'amount': sell_amount,
                        'high_watermark': executed_price,
                        'trailing': False,
                        'order_type': 'base'
                    }
                    
                    buy_msg = f"⚡ {symbol}: MARKET BOUGHT (Lvl 0) at {executed_price}"
                    print(buy_msg)
                    send_telegram(buy_msg)
                    
                    previous_price = executed_price
                    for i in range(1, levels + 1):
                        multiplier = step_multipliers[i-1] if i-1 < len(step_multipliers) else i
                        buy_price = previous_price * (1 - step_percent * multiplier)
                        safe_price = float(exchange.price_to_precision(symbol, buy_price))
                        
                        order = exchange.create_limit_buy_order(symbol, safe_amount, safe_price)
                        active_orders[order['id']] = {'symbol': symbol, 'side': 'buy', 'price': safe_price, 'level': i, 'amount': safe_amount, 'order_type': 'safety'}
                        previous_price = safe_price

                    save_orders(active_orders)
                    log_msg = f"✅ Grid for {symbol} successfully built."
                    print(log_msg)
                    send_telegram(log_msg)

                except Exception as e:
                    error_msg = f"❌ Error setting up grid for {symbol}: {e}. Skipping..."
                    print(error_msg)
                    send_telegram(error_msg)
                    continue
        
        if active_orders:
            msg = f"📂 Multi-bot restarted. {len(active_orders)} orders in memory."
            print(msg)
            send_telegram(msg)

    except Exception as e:
        print(f"❌ Startup error: {e}")
        return

    print("-" * 30)
    
    while True:
        try:
            try:
                tickers = exchange.fetch_tickers(SYMBOLS)
            except Exception as e:
                print(f"⚠️ Error fetching tickers: {e}")
                tickers = {}
                
            current_order_ids = list(active_orders.keys())
            
            for order_id in current_order_ids:
                if order_id not in active_orders:
                    continue
                    
                order_data = active_orders[order_id]
                symbol = order_data['symbol']
                
                if order_data['side'] == 'position':
                    if symbol not in tickers:
                        continue
                        
                    current_price = tickers[symbol]['last']
                    buy_price = order_data['buy_price']
                    amount = order_data['amount']
                    level = order_data['level']
                    order_type = order_data.get('order_type', 'base' if level == 0 else 'safety')
                    
                    current_activation = activation_base if order_type == 'base' else activation_safety
                    current_trailing = trailing_base if order_type == 'base' else trailing_safety
                    
                    if not order_data.get('trailing', False):
                        if current_price >= buy_price * (1 + current_activation):
                            order_data['trailing'] = True
                            order_data['high_watermark'] = current_price
                            log_msg = f"🚀 {symbol}: Trailing activated! (Lvl {level} - {order_type})\n🛒 Buy Price: {buy_price}\n📈 Current Price: {current_price}\n👀 Price went +{current_activation*100}%. Tracking peak, waiting for a {current_trailing*100}% pullback to sell."
                            print(log_msg)
                            send_telegram(log_msg)
                            save_orders(active_orders)
                    else:
                        high_watermark = order_data.get('high_watermark', buy_price)
                        if current_price > high_watermark:
                            order_data['high_watermark'] = current_price
                            save_orders(active_orders)
                        elif current_price <= high_watermark * (1 - current_trailing):
                            log_msg = f"🔥 {symbol}: Trailing caught a pullback. Market selling..."
                            print(log_msg)
                            try:
                                sell_order = exchange.create_market_sell_order(symbol, amount)
                                exec_sell_price = sell_order.get('average') or sell_order.get('price') or current_price
                                
                                buy_value = buy_price * amount
                                sell_value = exec_sell_price * amount
                                gross_profit = sell_value - buy_value
                                
                                total_fee = (buy_value * 0.001) + (sell_value * 0.001)
                                net_profit = gross_profit - total_fee
                                
                                profit_msg = (f"💸 {symbol}: SOLD (Lvl {level}) at {exec_sell_price}!\n"
                                              f"✅ Net Profit: ~{net_profit:.2f} USDT\n"
                                              f"📊 (Gross: +{gross_profit:.2f} $, Est. Fees (in+out): ~{total_fee:.2f} $)")
                                print(profit_msg)
                                send_telegram(profit_msg)
                                
                                del active_orders[order_id]
                                    
                                remaining_positions = [v for k, v in active_orders.items() if v['symbol'] == symbol and v['side'] == 'position']
                                
                                if not remaining_positions:
                                    try:
                                        exchange.cancel_all_orders(symbol)
                                    except Exception:
                                        pass
                                        
                                    keys_to_delete = [k for k, v in active_orders.items() if v['symbol'] == symbol and v['side'] == 'buy']
                                    for k in keys_to_delete:
                                        active_orders.pop(k, None)
                                        
                                    time.sleep(1)
                                    re_amount_coin = trade_amount_usdt / current_price
                                    re_safe_amount = float(exchange.amount_to_precision(symbol, re_amount_coin))
                                    grid_base_price = current_price
                                    try:
                                        re_market_order = exchange.create_market_buy_order(symbol, re_safe_amount)
                                        grid_base_price = re_market_order.get('average') or re_market_order.get('price') or current_price
                                        
                                        time.sleep(2)
                                        base_coin = symbol.split('/')[0]
                                        free_balance = exchange.fetch_balance().get(base_coin, {}).get('free', 0.0)
                                        actual_pos_amount = float(exchange.amount_to_precision(symbol, min(re_safe_amount, free_balance)))
                                        
                                        new_pos_id = f"pos_{symbol}_{int(time.time()*1000)}_0"
                                        active_orders[new_pos_id] = {
                                            'symbol': symbol, 'side': 'position', 'buy_price': grid_base_price, 
                                            'level': 0, 'amount': actual_pos_amount, 'high_watermark': grid_base_price, 'trailing': False, 'order_type': 'base'
                                        }
                                        log_msg_rebuy = f"♻️ {symbol}: Reinvest! Market re-entry (Lvl 0) at {grid_base_price}"
                                        print(log_msg_rebuy)
                                        send_telegram(log_msg_rebuy)
                                    except Exception as e:
                                        err_msg = f"❌ Reinvest error for {symbol}: {e}"
                                        print(err_msg)
                                        send_telegram(err_msg)

                                    new_amount_coin = trade_amount_usdt / grid_base_price
                                    new_safe_amount = float(exchange.amount_to_precision(symbol, new_amount_coin))
                                    
                                    previous_price = grid_base_price
                                    for i in range(1, levels + 1):
                                        multiplier = step_multipliers[i-1] if i-1 < len(step_multipliers) else i
                                        buy_price_limit = previous_price * (1 - step_percent * multiplier)
                                        safe_price = float(exchange.price_to_precision(symbol, buy_price_limit))
                                        
                                        order = exchange.create_limit_buy_order(symbol, new_safe_amount, safe_price)
                                        active_orders[order['id']] = {'symbol': symbol, 'side': 'buy', 'price': safe_price, 'level': i, 'amount': new_safe_amount, 'order_type': 'safety'}
                                        previous_price = safe_price
                                        
                                else:
                                    if level > 0:
                                        idx = level - 1
                                        multiplier = step_multipliers[idx] if idx < len(step_multipliers) else level
                                        buy_price_limit = exec_sell_price * (1 - step_percent * multiplier)
                                        safe_price = float(exchange.price_to_precision(symbol, buy_price_limit))
                                        
                                        new_amount_coin = trade_amount_usdt / safe_price
                                        new_safe_amount = float(exchange.amount_to_precision(symbol, new_amount_coin))
                                        
                                        order = exchange.create_limit_buy_order(symbol, new_safe_amount, safe_price)
                                        active_orders[order['id']] = {'symbol': symbol, 'side': 'buy', 'price': safe_price, 'level': level, 'amount': new_safe_amount, 'order_type': 'safety'}
                                        print(f"🔄 {symbol}: Restored BUY order for Lvl {level} at {safe_price}")
                                
                                status = get_status_report(exchange, active_orders)
                                send_telegram(f"📉 **Updated status after profit taking:**\n\n{status}")
                                save_orders(active_orders)
                            except Exception as e:
                                err_msg = f"❌ Market Sell error on trailing for {symbol}: {e}"
                                print(err_msg)
                                send_telegram(err_msg)
                    
                    continue

                order_info = exchange.fetch_order(order_id, symbol)
                
                if order_info['status'] == 'closed':
                    executed_price = order_data['price']
                    level = order_data['level']
                    amount = order_data['amount']
                    
                    log_msg = f"⚡ {symbol}: BOUGHT (Lvl {level}) at {executed_price}"
                    print(log_msg)
                    send_telegram(log_msg)
                    
                    base_coin = symbol.split('/')[0]
                    free_balance = exchange.fetch_balance()[base_coin]['free']
                    actual_amount = min(amount, free_balance)
                    safe_amount = float(exchange.amount_to_precision(symbol, actual_amount))
                    
                    pos_id = f"pos_{symbol}_{int(time.time()*1000)}_{level}"
                    active_orders[pos_id] = {
                        'symbol': symbol, 
                        'side': 'position', 
                        'buy_price': executed_price, 
                        'level': level, 
                        'amount': safe_amount,
                        'high_watermark': executed_price,
                        'trailing': False,
                        'order_type': 'safety'
                    }
                        
                    status = get_status_report(exchange, active_orders)
                    send_telegram(f"📉 **Updated status after trade:**\n\n{status}")
                        
                    del active_orders[order_id]
                    save_orders(active_orders)

            for symbol in SYMBOLS:
                symbol_orders = {oid: data for oid, data in active_orders.items() if data['symbol'] == symbol}
                if not symbol_orders:
                    continue
                
                if any(data['side'] == 'position' for data in symbol_orders.values()):
                    continue
                    
                max_buy_price = max(data['price'] for data in symbol_orders.values())
                
                try:
                    current_price = exchange.fetch_ticker(symbol)['last']
                    
                    if current_price > max_buy_price * 1.01:
                        log_msg = f"🚀 {symbol}: Price shot up ({current_price} > {max_buy_price}). Trailing Grid Up!"
                        print(log_msg)
                        send_telegram(log_msg)
                        
                        try:
                            exchange.cancel_all_orders(symbol)
                        except ccxt.ExchangeError:
                            pass
                        
                        for oid in list(symbol_orders.keys()):
                            active_orders.pop(oid, None)
                            
                        amount_coin = trade_amount_usdt / current_price
                        safe_amount = float(exchange.amount_to_precision(symbol, amount_coin))
                        
                        try:
                            market_order = exchange.create_market_buy_order(symbol, safe_amount)
                            executed_price = market_order.get('average') or market_order.get('price') or current_price
                            
                            time.sleep(2)
                            base_coin = symbol.split('/')[0]
                            free_balance = exchange.fetch_balance().get(base_coin, {}).get('free', 0.0)
                            actual_pos_amount = float(exchange.amount_to_precision(symbol, min(safe_amount, free_balance)))
                            
                            new_pos_id = f"pos_{symbol}_{int(time.time()*1000)}_0"
                            active_orders[new_pos_id] = {
                                'symbol': symbol, 'side': 'position', 'buy_price': executed_price, 
                                'level': 0, 'amount': actual_pos_amount, 'high_watermark': executed_price, 'trailing': False, 'order_type': 'base'
                            }
                            log_msg_rebuy = f"♻️ {symbol}: Grid pulled up and market entered (Lvl 0) at {executed_price}"
                            print(log_msg_rebuy)
                            send_telegram(log_msg_rebuy)
                        except Exception as e:
                            executed_price = current_price
                            print(f"❌ Entry error while pulling up grid for {symbol}: {e}")
                            
                        new_amount_coin = trade_amount_usdt / executed_price
                        new_safe_amount = float(exchange.amount_to_precision(symbol, new_amount_coin))
                        
                        previous_price = executed_price
                        for i in range(1, levels + 1):
                            multiplier = step_multipliers[i-1] if i-1 < len(step_multipliers) else i
                            buy_price = previous_price * (1 - step_percent * multiplier)
                            safe_price = float(exchange.price_to_precision(symbol, buy_price))
                            
                            order = exchange.create_limit_buy_order(symbol, safe_amount, safe_price)
                            active_orders[order['id']] = {'symbol': symbol, 'side': 'buy', 'price': safe_price, 'level': i, 'amount': safe_amount, 'order_type': 'safety'}
                            previous_price = safe_price
                            
                        save_orders(active_orders)
                except Exception as e:
                    print(f"⚠️ Error pulling up grid for {symbol}: {e}")

            time.sleep(3)
            
        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()