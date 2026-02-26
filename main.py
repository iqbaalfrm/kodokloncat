import time
import requests
import sqlite3
import pytz
import threading
import os
import html
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


def pre_block(lines):
    if isinstance(lines, list):
        lines = "\n".join(lines)
    return html.escape(lines)


def fmt_kv_row(label, value):
    return f"{label:<14} : {value}"


def fmt_sim_row(source, rate, value):
    return f"{source:<4} @ {rate:<5} : {fmt_rp(value)}"


def fmt_cuan_row(amount, value):
    return f"{int(amount/1000):>3}rb Riyal : +Rp {value:,.0f}"


def send_telegram_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )


def get_osl_spot_price():
    url = "https://api.koinsayang.com/api/spot/v1/market/ticker?symbol=USDTIDR_SPBL"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10).json()
    data = res.get("data") or {}

    # Prefer last traded price (`close`), fallback to top ask/bid when unavailable.
    for key in ("close", "sellOne", "buyOne"):
        value = data.get(key)
        if value is not None:
            return float(value)
    raise ValueError("OSL ticker price not found")


def get_p2p_api(fiat, trade_type, return_best=False, best_mode="max"):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    headers = {"User-Agent": "Mozilla/5.0"}
    payload = {
        "asset": "USDT", "fiat": fiat, "merchantCheck": True,
        "page": 1, "rows": 5, "tradeType": trade_type
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
                n = a['advertiser']['nickName'][:12]
                curr = "Rp" if fiat == "IDR" else "SR"
                lines.append(f"{n:<12} : {curr} {p:,.2f}")
        out_text = "\n".join(lines) if lines else "Market Offline"
        return (out_text, best_price) if return_best else out_text
    except:
        return ("Connection Error", None) if return_best else "Connection Error"


def get_market_data():
    try:
        # 1. Fetch Currency Rates
        sar_res = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
        google_sar = sar_res['rates']['IDR']

        toko_res = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
        tko_raw = float(toko_res['price'])
        try:
            osl_raw = get_osl_spot_price()
        except:
            osl_raw = tko_raw

        # 2. Logic Pajak (0.2222%)
        osl_net = osl_raw * (1 + 0.2222 / 100)

        # 3. Spot Prices + P2P snapshots
        try:
            idx = float(requests.get("https://indodax.com/api/ticker/usdtidr").json()['ticker']['last'])
        except:
            idx = osl_raw

        p2p_buy_indo_text, p2p_buy_indo_best = get_p2p_api('IDR', 'BUY', return_best=True, best_mode="min")
        p2p_sell_indo_text = get_p2p_api('IDR', 'SELL')
        p2p_buy_saudi_text = get_p2p_api('SAR', 'BUY')
        p2p_sell_saudi_text = get_p2p_api('SAR', 'SELL')

        tz = pytz.timezone('Asia/Jakarta')
        now_str = datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        # --- CONSTRUCT MESSAGE (HTML for cleaner Telegram layout) ---
        divs = [3.78, 3.785, 3.79, 3.795, 3.8]
        amts = [20000, 50000, 100000, 200000, 300000]

        parts = []
        parts.append("🐸 <b>KODOKLONCAT UPDATE</b>")
        parts.append(f"🕒 <b>{html.escape(now_str)} WIB</b>")
        parts.append(html.escape(SEP))

        ringkasan_rows = [
            fmt_kv_row("Google SAR", fmt_rp(google_sar)),
            fmt_kv_row("OSL Net", fmt_rp(osl_net)),
        ]
        if p2p_buy_indo_best:
            ringkasan_rows.append(fmt_kv_row("P2P Indo Buy", fmt_rp(p2p_buy_indo_best)))
        ringkasan_rows.append(fmt_kv_row("OSL @3.78", fmt_rp(osl_net / 3.78)))
        parts.append("📌 <b>RINGKASAN CEPAT</b>")
        parts.append(pre_block(ringkasan_rows))

        parts.append("1) <b>CURRENCY RATES</b>")
        parts.append(pre_block([
            fmt_kv_row("Google SAR", fmt_rp(google_sar)),
            fmt_kv_row("OSL", fmt_rp(osl_raw)),
            fmt_kv_row("+ Biaya 0.2%", fmt_rp(osl_net)),
        ]))

        parts.append("2) <b>INDONESIA SPOT</b> 🇮🇩")
        parts.append(pre_block([
            fmt_kv_row("Tokocrypto", fmt_rp(tko_raw, 0)),
            fmt_kv_row("Indodax", fmt_rp(idx, 0)),
            fmt_kv_row("Pintu Pro", fmt_rp(tko_raw, 0)),
            fmt_kv_row("OSL", fmt_rp(osl_raw, 0)),
        ]))

        parts.append("3) <b>SIMULASI SAR (OSL NET + FEE)</b>")
        parts.append(pre_block([fmt_sim_row("OSL", d, osl_net / d) for d in divs]))

        if p2p_buy_indo_best:
            parts.append("4) <b>SIMULASI SAR P2P (NO TAX)</b>")
            parts.append("<i>P2P Buy Indo termurah</i>")
            parts.append(pre_block([fmt_sim_row("P2P", d, p2p_buy_indo_best / d) for d in divs]))

        parts.append(html.escape(SEP))
        parts.append("5) <b>ESTIMASI CUAN OSL (Rate 3.78)</b>")
        parts.append("<i>Google SAR - Simulasi OSL (Net + Fee)</i>")
        untung_per_sar = google_sar - (osl_net / 3.78)
        parts.append(pre_block([fmt_cuan_row(a, untung_per_sar * a) for a in amts]))

        if p2p_buy_indo_best:
            parts.append("6) <b>ESTIMASI CUAN P2P (Rate 3.78)</b>")
            parts.append("<i>Google SAR - Simulasi P2P (No Tax, P2P Buy Indo termurah)</i>")
            untung_per_sar_p2p = google_sar - (p2p_buy_indo_best / 3.78)
            parts.append(pre_block([fmt_cuan_row(a, untung_per_sar_p2p * a) for a in amts]))

        parts.append(html.escape(SEP))
        parts.append("7) <b>P2P INDONESIA</b> 🇮🇩")
        parts.append("📱 <b>Buy</b>")
        parts.append(pre_block(p2p_buy_indo_text))
        parts.append("🛒 <b>Sell</b>")
        parts.append(pre_block(p2p_sell_indo_text))

        parts.append(html.escape(SEP))
        parts.append("8) <b>P2P SAUDI ARABIA</b> 🇸🇦")
        parts.append("📱 <b>Buy</b>")
        parts.append(pre_block(p2p_buy_saudi_text))
        parts.append("🛒 <b>Sell</b>")
        parts.append(pre_block(p2p_sell_saudi_text))

        return "\n".join(parts)
    except Exception as e:
        return f"<b>Error Fetching Data:</b> {html.escape(str(e))}"


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
                        send_telegram_message(
                            cid,
                            "🐸 <b>KODOKRIYAL AKTIF!</b>\nUpdate otomatis tiap 3 menit.",
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
                send_telegram_message(mid, msg)
            except:
                pass

        time.sleep(INTERVAL)


if __name__ == "__main__":
    setup_db()
    print(get_market_data())
    threading.Thread(target=listen_updates, daemon=True).start()
    print("🐸 KODOKRIYAL BOT v9.8 RUNNING...")
    broadcast_loop()
