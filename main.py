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
SEP = "──────────────────────"


def setup_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS members (chat_id INTEGER PRIMARY KEY, joined_at TEXT)''')
    conn.commit()
    conn.close()


def fmt_rp(value, decimals=2):
    return f"Rp {value:,.{decimals}f}"


def fmt_kv(label, value):
    return f"• {label:<12}: {value}\n"


def fmt_sim_line(source, rate, value):
    return f"• {source:<4}/ {rate:<5} : {fmt_rp(value)}\n"


def fmt_cuan_line(amount, value):
    return f"• {int(amount/1000):>3}rb Riyal: +Rp {value:,.0f}\n"


def get_p2p_api(fiat, trade_type, return_best=False, best_mode="max"):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"User-Agent": "Mozilla/5.0"}
    payload = {
        "asset": "USDT", "fiat": fiat, "merchantCheck": True,
        "page": 1, "rows": 8, "tradeType": trade_type
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10).json()
        lines = []
        best_price = None
        if 'data' in res:
            for a in res['data']:
                p = float(a['adv']['price'])
                if best_price is None:
                    best_price = p
                elif best_mode == "min" and p < best_price:
                    best_price = p
                elif best_mode != "min" and p > best_price:
                    best_price = p
                n = a['advertiser']['nickName'][:10].ljust(10)
                curr = "Rp " if fiat == "IDR" else "SR "
                lines.append(f"`{n}: {curr}{p:,.2f}`")
        out_text = "\n".join(lines) if lines else "• Market Offline"
        return (out_text, best_price) if return_best else out_text
    except:
        return ("• Connection Error", None) if return_best else "• Connection Error"


def get_market_data():
    try:
        # 1. Fetch Currency Rates
        sar_res = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
        google_sar = sar_res['rates']['IDR']

        toko_res = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
        tko_raw = float(toko_res['price'])

        # 2. Logic Pajak (0.2222%)
        tko_net = tko_raw * (1 + 0.2222 / 100)

        # 3. Spot Prices + P2P snapshots
        try:
            idx = float(requests.get("https://indodax.com/api/ticker/usdtidr").json()['ticker']['last'])
        except:
            idx = tko_raw

        p2p_buy_indo_text, p2p_buy_indo_best = get_p2p_api('IDR', 'BUY', return_best=True, best_mode="min")
        p2p_sell_indo_text = get_p2p_api('IDR', 'SELL')
        p2p_buy_saudi_text = get_p2p_api('SAR', 'BUY')
        p2p_sell_saudi_text = get_p2p_api('SAR', 'SELL')

        tz = pytz.timezone('Asia/Jakarta')
        now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        # --- CONSTRUCT MESSAGE ---
        msg = f"🐸 *KODOKLONCAT UPDATE*\n"
        msg += f"📅 `{now_str} WIB`\n"
        msg += f"{SEP}\n"
        msg += f"💱 *CURRENCY RATES*\n"
        msg += fmt_kv("Google SAR", fmt_rp(google_sar))
        msg += fmt_kv("Tokocrypto", fmt_rp(tko_raw))
        msg += fmt_kv("+ Biaya 0.2%", fmt_rp(tko_net))
        msg += "\n"

        msg += f"📊 *SIMULASI SAR (NET + FEE)*\n"
        divs = [3.78, 3.785, 3.79, 3.795, 3.8, 3.81, 3.82]
        for d in divs:
            msg += fmt_sim_line("Toko", d, tko_net / d)

        if p2p_buy_indo_best:
            msg += "\n"
            msg += f"📊 *SIMULASI SAR P2P (NO TAX, P2P Buy Indo Termurah)*\n"
            for d in divs:
                msg += fmt_sim_line("P2P", d, p2p_buy_indo_best / d)

        msg += f"{SEP}\n"
        msg += f"💰 *ESTIMASI CUAN TOKOCRYPTO (Rate 3.785)*\n"
        msg += f"_Untung Google SAR - Simulasi Tokocrypto (Net + Fee)_\n"
        untung_per_sar = google_sar - (tko_net / 3.785)
        amts = [20000, 50000, 100000, 200000, 300000]
        for a in amts:
            msg += fmt_cuan_line(a, untung_per_sar * a)

        if p2p_buy_indo_best:
            msg += "\n"
            msg += f"💰 *ESTIMASI CUAN P2P (Rate 3.785)*\n"
            msg += f"_Untung Google SAR - Simulasi P2P (No Tax, P2P Buy Indo Termurah)_\n"
            untung_per_sar_p2p = google_sar - (p2p_buy_indo_best / 3.785)
            for a in amts:
                msg += fmt_cuan_line(a, untung_per_sar_p2p * a)

        msg += f"{SEP}\n"
        msg += f"🇮🇩 *INDONESIA SPOT*\n"
        msg += fmt_kv("Tokocrypto", fmt_rp(tko_raw, 0))
        msg += fmt_kv("Indodax", fmt_rp(idx, 0))
        msg += fmt_kv("Pintu Pro", fmt_rp(tko_raw, 0))
        msg += fmt_kv("OSL", fmt_rp(tko_raw, 0))
        msg += "\n"

        msg += f"📱 *P2P Buy (Indo):*\n{p2p_buy_indo_text}\n"
        msg += f"🛒 *P2P Sell (Indo):*\n{p2p_sell_indo_text}\n"
        msg += f"{SEP}\n"
        msg += f"🇸🇦 *SAUDI ARABIA P2P*\n"
        msg += f"📱 *P2P Buy (Saudi):*\n{p2p_buy_saudi_text}\n"
        msg += f"🛒 *P2P Sell (Saudi):*\n{p2p_sell_saudi_text}"

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
                    if "message" not in upd:
                        continue
                    cid = upd["message"]["chat"]["id"]
                    txt = upd["message"].get("text", "")

                    if txt == "/start":
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute(
                            "INSERT OR IGNORE INTO members VALUES (?, ?)",
                            (cid, datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        )
                        conn.commit()
                        conn.close()
                        requests.post(
                            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                            data={
                                "chat_id": cid,
                                "text": "🐸 *KODOKRIYAL AKTIF!*\nUpdate otomatis tiap 3 menit.",
                                "parse_mode": "Markdown",
                            },
                        )
        except:
            time.sleep(5)


def broadcast_loop():
    while True:
        msg = get_market_data()
        conn = sqlite3.connect(DB_NAME)
        users = [r[0] for r in conn.execute("SELECT chat_id FROM members").fetchall()]
        conn.close()

        for mid in set(users + [ADMIN_ID]):
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                    data={"chat_id": mid, "text": msg, "parse_mode": "Markdown"},
                )
            except:
                pass

        time.sleep(INTERVAL)


if __name__ == "__main__":
    setup_db()
    threading.Thread(target=listen_updates, daemon=True).start()
    print("🐸 KODOKRIYAL BOT v9.8 RUNNING...")
    broadcast_loop()
