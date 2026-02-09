import time
import requests
import sqlite3
import pytz
import os
import sys
from datetime import datetime

# ================= CONFIGURATION =================
TOKEN = "8591550376:AAF0VMvdW5K376uJS17L9eQ9gmW21RwXwuQ"
DB_NAME = "kodok_public.db"
ADMIN_ID = 834018428 
INTERVAL = 180  # Kembali ke 3 menit (Ubah ke 5 jika masih debug)
# =================================================

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members (chat_id INTEGER PRIMARY KEY, joined_at TEXT)''')
    conn.commit()
    conn.close()

def get_market_data():
    data = {
        "rates": {"s_idr": 0, "u_idr": 0}, 
        "spots": {"Tokocrypto": 0, "Indodax": 0, "Pintu Pro": 0, "OSL": 0}, 
        "p2p": {"idr_buy": "• Offline", "idr_sell": "• Offline", "sar_buy": "• Offline", "sar_sell": "• Offline"}
    }
    try:
        # 1. Currency Rates & Binance Benchmark
        try:
            res_sar = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
            data['rates']['s_idr'] = res_sar['rates']['IDR']
            res_u = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
            u_idr = float(res_u['price'])
            data['rates']['u_idr'] = u_idr
        except: 
            u_idr = 16900 

        # 2. Spot Prices
        try:
            idx = float(requests.get("https://indodax.com/api/ticker/usdtidr", timeout=5).json()['ticker']['last'])
        except: idx = u_idr
        try:
            pnt_res = requests.get("https://api.pintu.co.id/v2/trade/price-changes", timeout=5).json()
            pnt = next((float(i['latestPrice']) for i in pnt_res['data'] if i['pair'].lower() == 'usdt/idr'), u_idr)
        except: pnt = u_idr
        
        data['spots'] = {'Tokocrypto': u_idr, 'Indodax': idx, 'Pintu Pro': pnt, 'OSL': u_idr}

        # 3. P2P Markets
        data['p2p'] = {
            "idr_buy": get_p2p_api('IDR', 'BUY'),
            "idr_sell": get_p2p_api('IDR', 'SELL'),
            "sar_buy": get_p2p_api('SAR', 'BUY'),
            "sar_sell": get_p2p_api('SAR', 'SELL')
        }
    except: pass
    return data

def get_p2p_api(fiat, trade_type):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
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
    except: return "• Connection Error"

def run_server():
    setup_db()
    tz = pytz.timezone('Asia/Jakarta')
    print("🐸 KODOKLONCAT v7.1 (Calculator) LIVE!")

    while True:
        try:
            # Handle Members
            upd_url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset=-1"
            upds = requests.get(upd_url, timeout=10).json()
            if upds.get("ok") and upds.get("result"):
                m = upds["result"][0].get("message", {})
                cid, txt = m.get("chat", {}).get("id"), m.get("text", "")
                if txt == "/start":
                    conn = sqlite3.connect(DB_NAME); conn.execute("INSERT OR IGNORE INTO members VALUES (?, ?)", (cid, datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S'))); conn.commit(); conn.close()
                    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": "🐸 *KODOKLONCAT PUBLIC*\nUpdate harga + Simulasi Kurs Aktif.", "parse_mode": "Markdown"})
                if cid == ADMIN_ID and txt == "/exit": sys.exit()

            # Broadcast Data
            d = get_market_data()
            now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')
            tko = d['spots']['Tokocrypto']
            
            p = f"🐸 *KODOKLONCAT UPDATE*\n📅 `{now_str} WIB`\n"
            p += f"──────────────────────\n💱 *CURRENCY RATES*\n"
            p += f"• `Google SAR : Rp {d['rates']['s_idr']:,.2f}`\n"
            p += f"• `Toko USDT  : Rp {tko:,.2f}`\n\n"
            
            p += f"📊 *SIMULASI KURS SAR (VIA TOKO)*\n"
            p += f"• `Toko / 3.78 : Rp {tko/3.78:,.2f}`\n"
            p += f"• `Toko / 3.79 : Rp {tko/3.79:,.2f}`\n"
            p += f"• `Toko / 3.80 : Rp {tko/3.80:,.2f}`\n"
            
            p += f"──────────────────────\n🇮🇩 *INDONESIA SPOT*\n"
            for name, price in d['spots'].items():
                p += f"• `{name.ljust(9)}: Rp {price:,.0f}`\n"
            
            p2p = d['p2p']
            p += f"\n📱 *P2P Buy (Indo):*\n{p2p['idr_buy']}\n🛒 *P2P Sell (Indo):*\n{p2p['idr_sell']}"
            p += f"\n──────────────────────\n🇸🇦 *SAUDI ARABIA P2P*\n"
            p += f"📱 *P2P Buy (Saudi):*\n{p2p['sar_buy']}\n🛒 *P2P Sell (Saudi):*\n{p2p['sar_sell']}"

            conn = sqlite3.connect(DB_NAME)
            users = [r[0] for r in conn.execute("SELECT chat_id FROM members").fetchall()]
            conn.close()
            
            for mid in set(users + [ADMIN_ID]):
                try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": mid, "text": p, "parse_mode": "Markdown"})
                except: pass

            time.sleep(INTERVAL)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(10)

if __name__ == "__main__":
    run_server()