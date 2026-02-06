import time
import requests
import sqlite3
import pytz
from datetime import datetime

# --- CONFIG ---
TOKEN = "8591550376:AAF0VMvdW5K376uJS17L9eQ9gmW21RwXwuQ"
DB_NAME = "kodok_private.db"
ADMIN_ID = 834018428 

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS whitelist 
                 (chat_id INTEGER PRIMARY KEY, added_at TEXT)''')
    conn.commit()
    conn.close()

def is_authorized(chat_id):
    if chat_id == ADMIN_ID: return True
    conn = sqlite3.connect(DB_NAME)
    res = conn.execute("SELECT 1 FROM whitelist WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()
    return True if res else False

def get_market_data():
    data = {"rates": {"s_idr": 0, "i_sar": 0, "u_idr": 0, "i_u": 0}, "spots": {}, "p2p": {}}
    try:
        res_sar = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=7).json()
        sar_to_idr = res_sar['rates']['IDR']
        res_usdt = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=7).json()
        u_idr = float(res_usdt['price'])
        data['rates'] = {'s_idr': sar_to_idr, 'i_sar': 1/sar_to_idr, 'u_idr': u_idr, 'i_u': 1/u_idr}

        idx_res = requests.get("https://indodax.com/api/ticker/usdtidr", timeout=5).json()
        idx = float(idx_res['ticker']['last'])
        
        pnt_res = requests.get("https://api.pintu.co.id/v2/trade/price-changes", timeout=5).json()
        pnt = 0
        for i in pnt_res['data']:
            if i['pair'].lower() == 'usdt/idr': pnt = float(i['latestPrice'])
        
        data['spots'] = {'Tokocrypto': u_idr, 'Indodax': idx, 'Pintu Pro': pnt, 'OSL': u_idr}
        data['p2p'] = {
            "idr_buy": get_p2p_api('IDR', 'BUY'), "idr_sell": get_p2p_api('IDR', 'SELL'),
            "sar_buy": get_p2p_api('SAR', 'BUY'), "sar_sell": get_p2p_api('SAR', 'SELL')
        }
    except Exception as e:
        print(f"Data Fetch Warning: {e}")
    return data

def get_p2p_api(fiat, trade_type):
    try:
        url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        payload = {"asset": "USDT", "fiat": fiat, "merchantCheck": True, "page": 1, "rows": 10, "tradeType": trade_type}
        res = requests.post(url, json=payload, timeout=7).json()
        symbol = "Rp" if fiat == "IDR" else "SR"
        text = ""
        if 'data' in res:
            for a in res['data']:
                p = float(a['adv']['price'])
                n = (a['advertiser']['nickName'][:10]).ljust(10)
                text += f"`{n} : {symbol} {p:,.2f}`\n"
            return text if text else "• No Sellers\n"
        return "• Offline\n"
    except: return "• Offline\n"

def run_server():
    setup_db()
    tz = pytz.timezone('Asia/Jakarta')
    print("🐸 KODOKLONCAT v6.2 (Zeabur Edition) DEPLOYED")

    while True:
        try:
            # 1. Handle Admin Commands & Whitelist
            upd_url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
            upds = requests.get(upd_url, timeout=5).json()
            if upds.get("ok") and upds.get("result"):
                m = upds["result"][0].get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "")

                if txt == "/start":
                    msg = "🐸 *KODOKLONCAT PRIVATE*" if is_authorized(cid) else f"🔒 *AKSES TERBATAS*\nID: `{cid}`"
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": msg, "parse_mode": "Markdown"})
                
                if cid == ADMIN_ID:
                    if txt.startswith("/add"):
                        target = int(txt.split(" ")[1])
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute("INSERT OR IGNORE INTO whitelist VALUES (?, ?)", (target, datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')))
                        conn.commit(); conn.close()
                        print(f"User {target} added to whitelist.")

            # 2. Build & Broadcast
            d = get_market_data()
            now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')
            
            p = f"🐸 *KODOKLONCAT PRIVATE*\n📅 `{now_str} WIB`\n"
            p += f"──────────────────────\n💱 *CURRENCY RATES*\n"
            p += f"• `1 SAR  = Rp {d['rates'].get('s_idr', 0):,.2f}`\n"
            p += f"• `1 IDR  = {d['rates'].get('i_sar', 0):.8f} SAR`\n"
            p += f"• `1 USDT = Rp {d['rates'].get('u_idr', 0):,.2f}`\n"
            p += f"• `1 IDR  = {d['rates'].get('i_u', 0):.8f} USDT`\n"
            p += f"──────────────────────\n\n🇮🇩 *INDONESIA MARKET*\n📈 *Spot Prices:*\n"
            
            for name, price in d.get('spots', {}).items():
                p += f"• `{name.ljust(9)}: Rp {price:,.0f}`\n"
            
            p2p = d.get('p2p', {})
            p += f"\n📱 *P2P Buy (Indo):*\n{p2p.get('idr_buy')}"
            p += f"\n🛒 *P2P Sell (Indo):*\n{p2p.get('idr_sell')}"
            p += f"\n──────────────────────\n\n🇸🇦 *SAUDI ARABIA MARKET*\n"
            p += f"📱 *P2P Buy (Saudi):*\n{p2p.get('sar_buy')}"
            p += f"\n🛒 *P2P Sell (Saudi):*\n{p2p.get('sar_sell')}"

            conn = sqlite3.connect(DB_NAME)
            users = [r[0] for r in conn.execute("SELECT chat_id FROM whitelist").fetchall()]
            conn.close()
            
            recipients = set(users + [ADMIN_ID])
            for mid in recipients:
                try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": mid, "text": p, "parse_mode": "Markdown"})
                except: pass

            print(f"Broadcast sent at {now_str}")
            time.sleep(60)
        except Exception as e:
            print(f"Server Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_server()