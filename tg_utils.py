import os
import requests

class TelegramManager:
    def __init__(self, token_env_key, chat_id_env_key):
        self.token_env_key = token_env_key
        self.chat_id_env_key = chat_id_env_key

    @property
    def token(self):
        return os.getenv(self.token_env_key)

    @property
    def chat_id(self):
        return os.getenv(self.chat_id_env_key)

    def send_message(self, text, reply_markup=None):
        if not self.token or not self.chat_id:
            print("Telegram configuration is missing. Cannot send message.")
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"TG Error: {e}")

    def handle_commands(self, exchange, active_orders, tickers, drop_steps, update_id_container):
        if not self.token or not self.chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            res = requests.get(url, params={'offset': update_id_container[0] + 1}, timeout=1).json()
            if res.get('ok') and res.get('result'):
                for update in res['result']:
                    update_id_container[0] = update['update_id']
                    msg = update.get('message', {})
                    if str(msg.get('chat', {}).get('id')) == str(self.chat_id) and msg.get('text') == '/status':
                        report = "📊 *STATUS REPORT*\n"
                        try:
                            balance = exchange.fetch_free_balance()
                            free_usdt = balance.get('USDT', 0)
                            report += f"💵 *Free USDT:* {free_usdt:.2f}\n\n"
                        except Exception:
                            report += f"💵 *Free USDT:* Error fetching\n\n"
                            
                        active_syms = set(v['symbol'] for v in active_orders.values())
                        if not active_syms:
                            self.send_message(report + "No active positions or orders.")
                            continue
                        
                        for sym in active_syms:
                            s_ords = [v for v in active_orders.values() if v['symbol'] == sym]
                            pos = [p for p in s_ords if p['side'] == 'position']
                            limits = [l for l in s_ords if l['side'] == 'buy']
                            cur_price = tickers.get(sym, {}).get('last', 0) if tickers else 0
                            
                            report += f"💎 *{sym}* | Price: {cur_price}\n"
                            
                            profit_data = active_orders.get(f"profit_{sym}", {})
                            total_profit = profit_data.get('total_usdt', 0.0)
                            if total_profit != 0:
                                report += f"   • Total Profit: 🏆 {total_profit:.2f} USDT\n"
                                
                            if pos:
                                total_amount = sum(p['amount'] for p in pos)
                                
                                invested_usdt = sum(p['buy_price'] * p['amount'] for p in pos)
                                avg_p = invested_usdt / total_amount if total_amount > 0 else 0
                                    
                                pnl = (cur_price/avg_p - 1)*100 if avg_p > 0 else 0
                                report += f"   • Invested: {invested_usdt:.2f} USDT\n"
                                report += f"   • Avg Entry: {avg_p:.4f} ({pnl:+.2f}%)\n"
                                report += f"   • Bought Levels:\n"
                                for p_item in sorted(pos, key=lambda x: x['level']):
                                    report += f"     - Lvl {p_item['level']} @ {p_item['buy_price']}\n"
                            else:
                                report += f"   • Avg Entry: None\n"
                            
                            if limits:
                                report += f"   • Active Limits:\n"
                                for l in sorted(limits, key=lambda x: x['level']):
                                    report += f"     - Lvl {l['level']} @ {l['price']}\n"
                            else:
                                report += f"   • Active Limits: None\n"
                            report += "\n"
                        self.send_message(report)
        except Exception:
            pass