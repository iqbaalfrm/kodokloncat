import time
import requests
import sqlite3
import pytz
import threading
import os
from datetime import datetime

# ================= CONFIGURATION =================
TOKEN = "8591550376:AAF0VMvdW5K376uJS17L9eQ9gmW21RwXwuQ"
ADMIN_ID = 834018428 
DB_NAME = "kodok_data.db"
INTERVAL = 180  # Broadcast tiap 3 menit
# =================================================

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS members (chat_id INTEGER PRIMARY KEY, joined_at TEXT)''')
    conn.commit()
    conn.close()

def get_p2p_api(fiat, trade_type):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"User-Agent": "Mozilla/5.0"}
    payload = {
        "asset": "USDT", "fiat": fiat, "merchantCheck": True, 
        "page": 1, "rows": 8, "tradeType": trade_type
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10).json()
        text = ""
        if 'data' in res:
            for a in res['data']:
                p = float(a['adv']['price'])
                n = a['advertiser']['nickName'][:10].ljust(10)
                curr = "Rp " if fiat == "IDR" else "SR "
                text += f"`{n}: {curr}{p:,.2f}`\n"
        return text if text else "• Market Offline"
    except:
        return "• Connection Error"

def get_market_data():
    try:
        # 1. Fetch Currency Rates
        sar_res = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
        google_sar = sar_res['rates']['IDR']
        
        toko_res = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
        tko_raw = float(toko_res['price'])
        
        # 2. Logic Pajak (0.2222%)
        tko_net = tko_raw * (1 + 0.2222 / 100)
        
        # 3. Spot Prices
        try: idx = float(requests.get("https://indodax.com/api/ticker/usdtidr").json()['ticker']['last'])
        except: idx = tko_raw

        tz = pytz.timezone('Asia/Jakarta')
        now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        # --- CONSTRUCT MESSAGE ---
        msg = f"🐸 *KODOKLONCAT UPDATE*\n"
        msg += f"📅 `{now_str} WIB`\n"
        msg += f"──────────────────────\n"
        msg += f"💱 *CURRENCY RATES*\n"
        msg += f"• Google SAR  : Rp {google_sar:,.2f}\n"
        msg += f"• Tokocrypto  : Rp {tko_raw:,.2f}\n"
        msg += f"• + Biaya 0.2%: Rp {tko_net:,.2f}\n\n"
        
        msg += f"📊 *SIMULASI SAR (NET + FEE)*\n"
        divs = [3.78, 3.785, 3.79, 3.795, 3.8, 3.81, 3.82]
        for d in divs:
            res_sim = tko_net / d
            msg += f"• Toko / {d} : Rp {res_sim:,.2f}\n"
        
        msg += f"──────────────────────\n"
        msg += f"💰 *ESTIMASI CUAN (Rate 3.79)*\n"
        msg += f"_Untung Google SAR - Simulasi_\n"
        untung_per_sar = google_sar - (tko_net / 3.79)
        amts = [20000, 50000, 100000, 200000, 300000]
        for a in amts:
            cuan = untung_per_sar * a
            msg += f"• {int(a/1000)}rb Riyal: +Rp {cuan:,.0f}\n"
            
        msg += f"──────────────────────\n"
        msg += f"🇮🇩 *INDONESIA SPOT*\n"
        msg += f"• Tokocrypto : Rp {tko_raw:,.0f}\n"
        msg += f"• Indodax    : Rp {idx:,.0f}\n"
        msg += f"• Pintu Pro  : Rp {tko_raw:,.0f}\n"
        msg += f"• OSL        : Rp {tko_raw:,.0f}\n\n"
        
        msg += f"📱 *P2P Buy (Indo):*\n{get_p2p_api('IDR', 'BUY')}\n"
        msg += f"🛒 *P2P Sell (Indo):*\n{get_p2p_api('IDR', 'SELL')}\n"
        msg += f"──────────────────────\n"
        msg += f"🇸🇦 *SAUDI ARABIA P2P*\n"
        msg += f"📱 *P2P Buy (Saudi):*\n{get_p2p_api('SAR', 'BUY')}\n"
        msg += f"🛒 *P2P Sell (Saudi):*\n{get_p2p_api('SAR', 'SELL')}"

        return msg
    except Exception as e:
        return f"Error Fetching Data: {e}"

def listen_updates():
    last_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}&timeout=30"
            res = requests.get(url, timeout=35).json()
            if res.get("ok") and res.get("result"):
                for upd in res["result"]:
                    last_id = upd["update_id"]
                    if "message" not in upd: continue
                    cid = upd["message"]["chat"]["id"]
                    txt = upd["message"].get("text", "")
                    
                    if txt == "/start":
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute("INSERT OR IGNORE INTO members VALUES (?, ?)", (cid, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                        conn.commit(); conn.close()
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": cid, "text": "🐸 *KODOKRIYAL AKTIF!*\nUpdate otomatis tiap 3 menit.", "parse_mode": "Markdown"})
        except: time.sleep(5)

def broadcast_loop():
    while True:
        msg = get_market_data()
        conn = sqlite3.connect(DB_NAME)
        users = [r[0] for r in conn.execute("SELECT chat_id FROM members").fetchall()]
        conn.close()
        
        for mid in set(users + [ADMIN_ID]):
            try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": mid, "text": msg, "parse_mode": "Markdown"})
            except: pass
        
        time.sleep(INTERVAL)

if __name__ == "__main__":
    setup_db()
    threading.Thread(target=listen_updates, daemon=True).start()
    print("🐸 KODOKRIYAL BOT v9.8 RUNNING...")
    broadcast_loop()