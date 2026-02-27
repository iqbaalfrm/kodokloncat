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
ADMIN_IDS = {279558348, 834018428}
DB_NAME = "kodok_data.db"
INTERVAL = 180  # Broadcast tiap 3 menit
DEPLOY_VERSION = os.getenv("DEPLOY_VERSION", "dev")
RESET_USERS_ON_DEPLOY = os.getenv("RESET_USERS_ON_DEPLOY", "1") == "1"
# =================================================
SEP = "──────────────────────"


def setup_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS members (chat_id INTEGER PRIMARY KEY, joined_at TEXT)''')
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS start_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            started_at TEXT NOT NULL
        )'''
    )
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )'''
    )
    deleted_users = apply_deploy_reset(conn)
    conn.commit()
    conn.close()
    return deleted_users


def apply_deploy_reset(conn):
    if not RESET_USERS_ON_DEPLOY:
        return 0

    last_version_row = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'last_deploy_version'"
    ).fetchone()
    last_version = last_version_row[0] if last_version_row else None

    if last_version == DEPLOY_VERSION:
        return 0

    deleted_users = conn.execute("DELETE FROM members").rowcount
    conn.execute(
        "INSERT OR REPLACE INTO app_meta(key, value) VALUES('last_deploy_version', ?)",
        (DEPLOY_VERSION,),
    )
    return deleted_users


def fmt_rp(value, decimals=2):
    return f"Rp {value:,.{decimals}f}"


def pre_block(lines):
    if isinstance(lines, list):
        lines = "\n".join(lines)
    return f"<pre>{html.escape(lines)}</pre>"


def fmt_kv_row(label, value):
    return f"{label:<14} : {value}"


def fmt_sim_row(source, rate, value):
    return f"{source:<4} @ {rate:<5} : {fmt_rp(value)}"


def fmt_cuan_row(amount, value):
    return f"{int(amount/1000):>3}rb Riyal : +Rp {value:,.0f}"


def wa_bullet(label, value):
    return f"• {label}: {value}"


def wa_sim_line(source, rate, value):
    return f"• {source} @ {rate}: {fmt_rp(value)}"


def wa_cuan_line(amount, value):
    return f"• {int(amount/1000)}rb Riyal: +Rp {value:,.0f}"


def wa_list_from_multiline(text):
    if not text:
        return "• -"
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return "• -"
    return "\n".join(f"• {ln}" for ln in lines)


def send_telegram_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )


def get_users_report():
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute(
        "SELECT chat_id, joined_at FROM members ORDER BY joined_at DESC"
    ).fetchall()
    conn.close()

    parts = []
    parts.append("👥 <b>DAFTAR USER BOT</b>")
    parts.append(f"Total user: <b>{len(rows)}</b>")
    parts.append(html.escape(SEP))

    if not rows:
        parts.append("Belum ada user.")
        return "\n".join(parts)

    lines = [f"{i}. {chat_id} | {joined_at}" for i, (chat_id, joined_at) in enumerate(rows, 1)]
    # Telegram message limit safety
    body = "\n".join(lines)
    parts.append(pre_block(body[:3500]))
    return "\n".join(parts)


def get_users_history_report(limit=50):
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute(
        "SELECT chat_id, started_at FROM start_history ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    unique_total = conn.execute(
        "SELECT COUNT(DISTINCT chat_id) FROM start_history"
    ).fetchone()[0]
    events_total = conn.execute("SELECT COUNT(*) FROM start_history").fetchone()[0]
    conn.close()

    parts = []
    parts.append("🗂️ <b>RIWAYAT /start</b>")
    parts.append(f"Total event /start: <b>{events_total}</b>")
    parts.append(f"Total user unik: <b>{unique_total}</b>")
    parts.append(html.escape(SEP))

    if not rows:
        parts.append("Belum ada riwayat /start.")
        return "\n".join(parts)

    lines = [f"{i}. {chat_id} | {started_at}" for i, (chat_id, started_at) in enumerate(rows, 1)]
    body = "\n".join(lines)
    parts.append(pre_block(body[:3500]))
    return "\n".join(parts)


def get_admin_users_menu():
    return "\n".join(
        [
            "🛠️ <b>MENU MANAJEMEN USER</b>",
            html.escape(SEP),
            "<code>/users</code> - daftar user aktif",
            "<code>/users_history [limit]</code> - riwayat klik /start",
            "<code>/user_remove &lt;chat_id&gt;</code> - hapus 1 user aktif",
            "<code>/users_clear</code> - hapus semua user aktif",
            "<code>/admin_users</code> - tampilkan menu ini",
        ]
    )


def remove_active_user(chat_id):
    conn = sqlite3.connect(DB_NAME)
    deleted = conn.execute("DELETE FROM members WHERE chat_id = ?", (chat_id,)).rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def clear_all_active_users():
    conn = sqlite3.connect(DB_NAME)
    deleted = conn.execute("DELETE FROM members").rowcount
    conn.commit()
    conn.close()
    return deleted


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
        parts.append(f"🕒 <code>{html.escape(now_str)} WIB</code>")
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
            fmt_kv_row("OSL", fmt_rp(osl_raw, 0)),
            fmt_kv_row("Tokocrypto", fmt_rp(tko_raw, 0)),
            fmt_kv_row("Indodax", fmt_rp(idx, 0)),
            fmt_kv_row("Pintu Pro", fmt_rp(tko_raw, 0)),
        ]))

        parts.append("3) <b>P2P INDONESIA BUY</b> 🇮🇩")
        parts.append("📱 <b>Buy</b>")
        parts.append(pre_block(p2p_buy_indo_text))

        parts.append("4) <b>SIMULASI SAR (OSL NET + FEE)</b>")
        parts.append(pre_block([fmt_sim_row("OSL", d, osl_net / d) for d in divs]))

        if p2p_buy_indo_best:
            parts.append("5) <b>SIMULASI SAR P2P (NO TAX)</b>")
            parts.append("<i>P2P Buy Indo termurah</i>")
            parts.append(pre_block([fmt_sim_row("P2P", d, p2p_buy_indo_best / d) for d in divs]))

        parts.append(html.escape(SEP))
        parts.append("6) <b>ESTIMASI CUAN OSL (Rate 3.78)</b>")
        parts.append("<i>Google SAR - Simulasi OSL (Net + Fee)</i>")
        untung_per_sar = google_sar - (osl_net / 3.78)
        parts.append(pre_block([fmt_cuan_row(a, untung_per_sar * a) for a in amts]))

        if p2p_buy_indo_best:
            parts.append("7) <b>ESTIMASI CUAN P2P (Rate 3.78)</b>")
            parts.append("<i>Google SAR - Simulasi P2P (No Tax, P2P Buy Indo termurah)</i>")
            untung_per_sar_p2p = google_sar - (p2p_buy_indo_best / 3.78)
            parts.append(pre_block([fmt_cuan_row(a, untung_per_sar_p2p * a) for a in amts]))

        parts.append(html.escape(SEP))
        parts.append("8) <b>P2P INDONESIA</b> 🇮🇩")
        parts.append("🛒 <b>Sell</b>")
        parts.append(pre_block(p2p_sell_indo_text))

        parts.append(html.escape(SEP))
        parts.append("9) <b>P2P SAUDI ARABIA</b> 🇸🇦")
        parts.append("📱 <b>Buy</b>")
        parts.append(pre_block(p2p_buy_saudi_text))
        parts.append("🛒 <b>Sell</b>")
        parts.append(pre_block(p2p_sell_saudi_text))

        return "\n".join(parts)
    except Exception as e:
        return f"<b>Error Fetching Data:</b> <code>{html.escape(str(e))}</code>"


def get_market_data_wa():
    try:
        sar_res = requests.get("https://api.exchangerate-api.com/v4/latest/SAR", timeout=10).json()
        google_sar = sar_res['rates']['IDR']

        toko_res = requests.get("https://api.binance.me/api/v3/ticker/price?symbol=USDTIDR", timeout=10).json()
        tko_raw = float(toko_res['price'])
        try:
            osl_raw = get_osl_spot_price()
        except:
            osl_raw = tko_raw

        osl_net = osl_raw * (1 + 0.2222 / 100)

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

        divs = [3.78, 3.785, 3.79, 3.795, 3.8]
        amts = [20000, 50000, 100000, 200000, 300000]

        parts = []
        parts.append("🐸 <b>KODOKLONCAT UPDATE (WA-FRIENDLY)</b>")
        parts.append(f"🕒 <b>{html.escape(now_str)} WIB</b>")
        parts.append(html.escape(SEP))

        parts.append("📌 <b>RINGKASAN CEPAT</b>")
        ringkasan = [
            wa_bullet("Google SAR", fmt_rp(google_sar)),
            wa_bullet("OSL Net", fmt_rp(osl_net)),
        ]
        if p2p_buy_indo_best:
            ringkasan.append(wa_bullet("P2P Indo Buy", fmt_rp(p2p_buy_indo_best)))
        ringkasan.append(wa_bullet("OSL @3.78", fmt_rp(osl_net / 3.78)))
        parts.append(html.escape("\n".join(ringkasan)))

        parts.append("1) <b>CURRENCY RATES</b>")
        parts.append(html.escape("\n".join([
            wa_bullet("Google SAR", fmt_rp(google_sar)),
            wa_bullet("OSL", fmt_rp(osl_raw)),
            wa_bullet("+ Biaya 0.2%", fmt_rp(osl_net)),
        ])))

        parts.append("2) <b>INDONESIA SPOT</b> 🇮🇩")
        parts.append(html.escape("\n".join([
            wa_bullet("OSL", fmt_rp(osl_raw, 0)),
            wa_bullet("Tokocrypto", fmt_rp(tko_raw, 0)),
            wa_bullet("Indodax", fmt_rp(idx, 0)),
            wa_bullet("Pintu Pro", fmt_rp(tko_raw, 0)),
        ])))

        parts.append("3) <b>P2P INDONESIA BUY</b> 🇮🇩")
        parts.append("📱 <b>Buy</b>")
        parts.append(html.escape(wa_list_from_multiline(p2p_buy_indo_text)))

        parts.append("4) <b>SIMULASI SAR (OSL NET + FEE)</b>")
        parts.append(html.escape("\n".join([wa_sim_line("OSL", d, osl_net / d) for d in divs])))

        if p2p_buy_indo_best:
            parts.append("5) <b>SIMULASI SAR P2P (NO TAX)</b>")
            parts.append("<i>P2P Buy Indo termurah</i>")
            parts.append(html.escape("\n".join([wa_sim_line("P2P", d, p2p_buy_indo_best / d) for d in divs])))

        parts.append(html.escape(SEP))
        parts.append("6) <b>ESTIMASI CUAN OSL (Rate 3.78)</b>")
        parts.append("<i>Google SAR - Simulasi OSL (Net + Fee)</i>")
        untung_per_sar = google_sar - (osl_net / 3.78)
        parts.append(html.escape("\n".join([wa_cuan_line(a, untung_per_sar * a) for a in amts])))

        if p2p_buy_indo_best:
            parts.append("7) <b>ESTIMASI CUAN P2P (Rate 3.78)</b>")
            parts.append("<i>Google SAR - Simulasi P2P (No Tax, P2P Buy Indo termurah)</i>")
            untung_per_sar_p2p = google_sar - (p2p_buy_indo_best / 3.78)
            parts.append(html.escape("\n".join([wa_cuan_line(a, untung_per_sar_p2p * a) for a in amts])))

        parts.append(html.escape(SEP))
        parts.append("8) <b>P2P INDONESIA</b> 🇮🇩")
        parts.append("🛒 <b>Sell</b>")
        parts.append(html.escape(wa_list_from_multiline(p2p_sell_indo_text)))

        parts.append(html.escape(SEP))
        parts.append("9) <b>P2P SAUDI ARABIA</b> 🇸🇦")
        parts.append("📱 <b>Buy</b>")
        parts.append(html.escape(wa_list_from_multiline(p2p_buy_saudi_text)))
        parts.append("🛒 <b>Sell</b>")
        parts.append(html.escape(wa_list_from_multiline(p2p_sell_saudi_text)))

        return "\n".join(parts)
    except Exception as e:
        return f"<b>Error Fetching Data:</b> <code>{html.escape(str(e))}</code>"


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
                    txt = (upd["message"].get("text", "") or "").strip()

                    if txt.startswith("/start"):
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        conn = sqlite3.connect(DB_NAME)
                        conn.execute(
                            "INSERT INTO start_history(chat_id, started_at) VALUES (?, ?)",
                            (cid, now_str),
                        )
                        conn.execute(
                            """INSERT INTO members(chat_id, joined_at) VALUES (?, ?)
                            ON CONFLICT(chat_id) DO UPDATE SET joined_at = excluded.joined_at""",
                            (cid, now_str),
                        )
                        conn.commit()
                        conn.close()
                        send_telegram_message(
                            cid,
                            "🐸 <b>KODOKRIYAL AKTIF!</b>\nUpdate otomatis tiap 3 menit.",
                        )
                    elif txt == "/wa":
                        send_telegram_message(cid, get_market_data_wa())
                    elif txt == "/tg":
                        send_telegram_message(cid, get_market_data())
                    elif txt == "/admin_users":
                        if cid in ADMIN_IDS:
                            send_telegram_message(cid, get_admin_users_menu())
                        else:
                            send_telegram_message(cid, "❌ <b>Akses ditolak</b>")
                    elif txt == "/users":
                        if cid in ADMIN_IDS:
                            send_telegram_message(cid, get_users_report())
                        else:
                            send_telegram_message(cid, "❌ <b>Akses ditolak</b>")
                    elif txt.startswith("/users_history"):
                        if cid not in ADMIN_IDS:
                            send_telegram_message(cid, "❌ <b>Akses ditolak</b>")
                            continue
                        limit = 50
                        parts = txt.split()
                        if len(parts) > 1:
                            try:
                                limit = max(1, min(200, int(parts[1])))
                            except:
                                limit = 50
                        send_telegram_message(cid, get_users_history_report(limit))
                    elif txt.startswith("/user_remove"):
                        if cid not in ADMIN_IDS:
                            send_telegram_message(cid, "❌ <b>Akses ditolak</b>")
                            continue
                        parts = txt.split()
                        if len(parts) != 2:
                            send_telegram_message(cid, "Format: <code>/user_remove 123456789</code>")
                            continue
                        try:
                            target = int(parts[1])
                        except:
                            send_telegram_message(cid, "chat_id harus angka.")
                            continue
                        removed = remove_active_user(target)
                        if removed:
                            send_telegram_message(cid, f"✅ User <code>{target}</code> dihapus dari user aktif.")
                        else:
                            send_telegram_message(cid, f"ℹ️ User <code>{target}</code> tidak ditemukan di user aktif.")
                    elif txt == "/users_clear":
                        if cid not in ADMIN_IDS:
                            send_telegram_message(cid, "❌ <b>Akses ditolak</b>")
                            continue
                        deleted = clear_all_active_users()
                        send_telegram_message(cid, f"✅ Semua user aktif dibersihkan. Total terhapus: <b>{deleted}</b>")
        except:
            time.sleep(5)


def broadcast_loop():
    while True:
        msg = get_market_data()
        conn = sqlite3.connect(DB_NAME)
        users = [r[0] for r in conn.execute("SELECT chat_id FROM members").fetchall()]
        conn.close()

        for mid in set(users + list(ADMIN_IDS)):
            try:
                send_telegram_message(mid, msg)
            except:
                pass

        time.sleep(INTERVAL)


if __name__ == "__main__":
    deleted_users = setup_db()
    if deleted_users:
        print(f"[DEPLOY RESET] Active users cleared: {deleted_users} (DEPLOY_VERSION={DEPLOY_VERSION})")
    print(get_market_data())
    threading.Thread(target=listen_updates, daemon=True).start()
    print("🐸 KODOKRIYAL BOT v9.8 RUNNING...")
    broadcast_loop()
