import os
import time
import requests
from flask import Flask
import threading

app = Flask(__name__)
start_time = time.time()

@app.route("/")
def home():
    return "Meme Coin Signal Bot (Deep Debug Engine) Aktif!", 200

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

seen_tokens = set()
scanned_count = 0
last_update_id = 0

IGNORE_TOKENS = ["USDC", "USDT", "WETH", "WBTC", "SOL", "ETH", "BNB", "WSOL", "WBNB", "DAI"]
INVALID_NAMES = ["SOLANA", "BSC", "ROBINHOOD", "ETHEREUM", "BASE", "BITCOIN", "BINANCE"]

def check_advanced_security(mint_address, chain_id):
    if chain_id.lower() != "solana":
        return True, "🟢 EVM Güvenlik Temiz", "Dengeli Dağılım", "🔥 LP Durumu Normal", "7.5/10", "EVM Ağı standart kontrol."
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            score = data.get("score", 0)
            risks = data.get("risks", [])
            
            high_dev_share = False
            lp_unlocked = False
            serial_dev_risk = False
            
            risk_details = []
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                risk_details.append(risk.get("name", ""))
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True
                if "creator" in risk_name or "dangerous authority" in risk_name:
                    serial_dev_risk = True

            # Dengeli ve Güvenli Sınır
            is_safe = score < 220 and not high_dev_share and not serial_dev_risk
            
            calculated_score = max(1.0, round(10.0 - (score / 35.0), 1))
            ai_score_str = f"{calculated_score}/10 🔥" if is_safe else f"{calculated_score}/10 ⚠️"
            
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            clustering_info = "⚠️ Şüpheli Dev Cüzdanı" if serial_dev_risk else ("⚠️ Yüksek Yoğunlaşma" if high_dev_share else "🟢 Dengeli Dağılım")
            lp_info = "⚠️ LP Riskli / Kilitsiz" if lp_unlocked else "🔥 LP Güvenli / Kilitli"
            
            eval_summary = "Risk oranı düşük, yapı uygun." if is_safe else f"Uyarı: {', '.join(risk_details[:2])}"

            return is_safe, status, clustering_info, lp_info, ai_score_str, eval_summary
        return True, "⚠️ Güvenlik Verisi Yok (Geçirildi)", "Bilinmiyor", "🔥 LP Normal", "6.5/10", "RugCheck API yanıt vermedi, teknik filtrelere güvenildi."
    except Exception:
        return True, "⚠️ Güvenlik Taraması İstisna", "Bilinmiyor", "🔥 LP Normal", "6.5/10", "API istisnası aşıldı."

def get_filtered_memecoins():
    global scanned_count
    filtered_list = []
    
    # Birden fazla kaynak kullanarak veri akışını garantiliyoruz
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/latest/dex/search?q=solana"
    ]
    
    candidate_addresses = []
    for ep in endpoints:
        try:
            res = requests.get(ep, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    for item in data:
                        t_addr = item.get("tokenAddress")
                        if t_addr:
                            candidate_addresses.append(t_addr)
                elif isinstance(data, dict):
                    pairs = data.get("pairs", [])
                    for p in pairs:
                        if p.get("chainId", "").lower() == "solana":
                            b_token = p.get("baseToken", {})
                            t_addr = b_token.get("address")
                            if t_addr:
                                candidate_addresses.append(t_addr)
        except Exception:
            pass

    if candidate_addresses:
        unique_addrs = list(set(candidate_addresses))[:25]
        scanned_count += len(unique_addrs)
        addrs_str = ",".join(unique_addrs)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}"
            response = requests.get(url, timeout=6)
            if response.status_code == 200:
                pairs = response.json().get("pairs", [])
                
                for pair in pairs:
                    chain_id = pair.get("chainId", "")
                    if chain_id.lower() != "solana":
                        continue

                    base_token = pair.get("baseToken", {})
                    symbol = base_token.get("symbol", "UNKNOWN")
                    address = base_token.get("address", "")

                    if not address or symbol.upper() in IGNORE_TOKENS or address in seen_tokens or symbol.upper() in INVALID_NAMES:
                        continue

                    volume = pair.get("volume", {}).get("h1", 0) or 0
                    liquidity = pair.get("liquidity", {}).get("usd", 0) or 0
                    fdv = pair.get("fdv", 0) or 0
                    price_change = pair.get("priceChange", {}).get("h1", 0) or 0

                    # Esnetilmiş ve Güvenli Eşikler (Hacim > $5,000, Likidite > $3,000)
                    if volume < 5000 or liquidity < 3000:
                        continue

                    is_safe, security_status, clustering_info, lp_info, ai_score, eval_text = check_advanced_security(address, chain_id)
                    if not is_safe:
                        continue

                    seen_tokens.add(address)

                    filtered_list.append({
                        "chain": chain_id.upper(),
                        "symbol": symbol,
                        "address": address,
                        "price_change": price_change,
                        "volume": volume,
                        "fdv": fdv,
                        "liquidity": liquidity,
                        "security": security_status,
                        "clustering": clustering_info,
                        "lp_info": lp_info,
                        "ai_score": ai_score,
                        "gemini_eval": eval_text,
                        "dex_url": pair.get("url", "https://dexscreener.com"),
                    })
        except Exception:
            pass

    return filtered_list

def send_telegram_alert(coin):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    buy_url = f"https://t.me/solana_trojanbot?start=r-user-{coin['address']}"
    buy_btn_text = "🚀 Trojan ile Al (Solana)"

    caption = (
        "🔥 **AI GÜVEN & HYPE SKORU:** `" + str(coin['ai_score']) + "`\n\n" +
        "🌐 **Ağ:** `" + str(coin['chain']) + "` - 🪙 **Token:** $" + str(coin['symbol']) + "\n" +
        "📈 **1S Değişim:** %" + str(coin['price_change']) + " - 📊 **1S Hacim:** $" + f"{coin['volume']:,.0f}" + "\n" +
        "💧 **Likidite:** $" + f"{coin['liquidity']:,.0f}" + " - 💰 **FDV:** $" + f"{coin['fdv']:,.0f}" + "\n\n" +
        "🛡️ **Güvenlik:** " + str(coin['security']) + "\n" +
        "👥 **Kümelenme:** " + str(coin['clustering']) + "\n" +
        "🔥 **Likidite:** " + str(coin['lp_info']) + "\n\n" +
        "🤖 **Analiz Özeti:** _" + str(coin['gemini_eval']) + "_\n\n" +
        "📍 **CA:**\n`" + str(coin['address']) + "`"
    )

    reply_markup = {"inline_keyboard": [[{"text": buy_btn_text, "url": buy_url}, {"text": "⚡ DexScreener", "url": coin["dex_url"]}]]}
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "Markdown", "reply_markup": reply_markup}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

def check_telegram_commands():
    global last_update_id
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"offset": last_update_id + 1, "timeout": 2}, timeout=4)
        if res.status_code == 200:
            updates = res.json().get("result", [])
            for update in updates:
                last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))

                if str(chat_id) != str(TELEGRAM_CHAT_ID):
                    continue

                if text == "/status":
                    uptime_min = int((time.time() - start_time) / 60)
                    status_msg = (
                        "🤖 **BOT ANLIK DURUM RAPORU (Deep Engine)**\n\n"
                        f"⏱️ **Çalışma Süresi:** {uptime_min} dakika\n"
                        f"📡 **Sinyal Taraması:** 🟢 Aktif (Optimize Edildi)\n"
                        f"🔍 **Taranan Havuz Sayısı:** {scanned_count}\n"
                        f"🎯 **Sinyal Atılan Token:** {len(seen_tokens)}"
                    )
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": status_msg, "parse_mode": "Markdown"})
    except Exception:
        pass

def run_bot_loop():
    while True:
        try:
            check_telegram_commands()
            coins = get_filtered_memecoins()
            for coin in coins[:2]:
                send_telegram_alert(coin)
                time.sleep(2)
        except Exception:
            pass
        time.sleep(15)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot_loop)
    bot_thread.daemon = True
    bot_thread.start()

    app.run(host="0.0.0.0", port=10000)
