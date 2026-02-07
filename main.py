import time
import requests
import sqlite3
import pytz
import os
from datetime import datetime

# --- CONFIG ---
TOKEN = "8591550376:AAF0VMvdW5K376uJS17L9eQ9gmW21RwXwuQ"
# Di Zeabur, sebaiknya simpan di folder /tmp atau gunakan Volume agar awet
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
    try:
        conn = sqlite3.connect(DB_NAME)
        res = conn.execute("SELECT 1 FROM whitelist WHERE chat_id=?", (chat_id,)).fetchone()
        conn.close()
        return True if res else False
    except: return False

def get_market_data():
    # Inisialisasi data default biar nggak 'None'
    data = {
        "rates": {"s_idr": 0, "i_sar": 0, "u_idr": 0, "i_u": 0}, 
        "spots": {"Tokocrypto": 0, "Indodax": 0, "Pintu Pro": 0, "OSL": 0}, 
        "p2p": {"idr_buy": "• Offline", "idr_sell": "• Offline", "sar_buy": "• Offline", "sar_sell": "• Offline"}
    }
    try:
        # 1. Currency Rates
        res_sar = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
        sar_to_idr = res_sar['rates']['IDR']
        
        res_u = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
        u_idr = float(res_u['price'])
        data['rates'] = {'s_idr': sar_to_idr, 'i_sar': 1/sar_to_idr, 'u_idr': u_idr, 'i_u': 1/u_idr}

        # 2. Spot Prices
        try:
            idx = float(requests.get("https://indodax.com/api/ticker/usdtidr", timeout=5).json()['ticker']['last'])
            pnt_res = requests.get("https://api.pintu.co.id/v2/trade/price-changes", timeout=5).json()
            pnt = next((float(i['latestPrice']) for i in pnt_res['data'] if i['pair'] == 'usdt/idr'), 0)
            data['spots'] = {'Tokocrypto': u_idr, 'Indodax': idx, 'Pintu Pro': pnt, 'OSL': u_idr}
        except: pass

        # 3. P2P Markets (Pake Header biar nggak di-block)
        data['p2p'] = {
            "idr_buy": get_p2p_api('IDR', 'BUY'),
            "idr_sell": get_p2p_api('IDR', 'SELL'),
            "sar_buy": get_p2p_api('SAR', 'BUY'),
            "sar_sell": get_p2p_api('SAR', 'SELL')
        }
    except Exception as e:
        print(f"Global Error: {e}")
    return data

def get_p2p_api(fiat, trade_type):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }
    payload = {"asset": "USDT", "fiat": fiat, "merchantCheck": True, "page": 1, "rows": 10, "tradeType": trade_type}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10).json()
        text = ""
        if 'data' in res and res['data']:
            for a in res['data']:
                p = float(a['adv']['price'])
                n = a['advertiser']['nickName'][:10].ljust(10)
                text += f"`{n} : {'Rp' if fiat == 'IDR' else 'SR'} {p:,.2f}`\n"
            return text if text else "• No Sellers"
        return "• Market Busy"
    except:
        return "• Connection Error"

def run_server():
    setup_db()
    tz = pytz.timezone('Asia/Jakarta')
    print("🐸 KODOKLONCAT Zeabur Ready!")

    while True:
        try:
            # Sync Admin/Whitelist
            upd_url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
            upds = requests.get(upd_url, timeout=10).json()
            if upds.get("ok") and upds.get("result"):
                m = upds["result"][0].get("message", {})
                cid = m.get("chat", {}).get("id")
                txt = m.get("text", "")
                
                if txt == "/start":
                    msg = "🐸 *KODOKLONCAT PRIVATE*" if is_authorized(cid) else f"🔒 *AKSES TERBATAS*\nID: `{cid}`"
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": msg, "parse_mode": "Markdown"})
                
                if cid == ADMIN_ID and txt.startswith("/add"):
                    target = int(txt.split(" ")[1])
                    conn = sqlite3.connect(DB_NAME)
                    conn.execute("INSERT OR IGNORE INTO whitelist VALUES (?, ?)", (target, datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')))
                    conn.commit(); conn.close()
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": ADMIN_ID, "text": f"✅ ID {target} ditambahkan."})

            # Broadcast Data
            d = get_market_data()
            now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')
            
            p = f"🐸 *KODOKLONCAT PRIVATE*\n📅 `{now_str} WIB`\n"
            p += f"──────────────────────\n💱 *CURRENCY RATES*\n"
            p += f"• `1 SAR  = Rp {d['rates'].get('s_idr', 0):,.2f}`\n"
            p += f"• `1 IDR  = {d['rates'].get('i_sar', 0):.8f} SAR`\n"
            p += f"• `1 USDT = Rp {d['rates'].get('u_idr', 0):,.2f}`\n"
            p += f"• `1 IDR  = {d['rates'].get('i_u', 0):.8f} USDT`\n"
            p += f"──────────────────────\n\n🇮🇩 *INDONESIA MARKET*\n📈 *Spot Prices:*\n"
            
            # Loop bursa biar nggak ilang
            for name, price in d.get('spots', {}).items():
                p += f"• `{name.ljust(9)}: Rp {price:,.0f}`\n"
            
            p2p = d.get('p2p', {})
            p += f"\n📱 *P2P Buy (Indo):*\n{p2p.get('idr_buy')}\n🛒 *P2P Sell (Indo):*\n{p2p.get('idr_sell')}"
            p += f"\n──────────────────────\n\n🇸🇦 *SAUDI ARABIA MARKET*\n"
            p += f"📱 *P2P Buy (Saudi):*\n{p2p.get('sar_buy')}\n🛒 *P2P Sell (Saudi):*\n{p2p.get('sar_sell')}"

            conn = sqlite3.connect(DB_NAME)
            users = [r[0] for r in conn.execute("SELECT chat_id FROM whitelist").fetchall()]
            conn.close()
            
            for mid in set(users + [ADMIN_ID]):
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": mid, "text": p, "parse_mode": "Markdown"})

            time.sleep(60)
        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_server()