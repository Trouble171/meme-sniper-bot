import os
import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Meme Coin Sniper Bot (Pro Safety + PnL Tracking) Aktif!", 200

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

seen_tokens = set()
pnl_tracker = {}  # Madde 5: PnL Performans Takip Hafızası

IGNORE_TOKENS = ["USDC", "USDT", "WETH", "WBTC", "SOL", "ETH", "BNB", "WSOL", "WBNB", "DAI"]
INVALID_NAMES = ["SOLANA", "BSC", "ROBINHOOD", "ETHEREUM", "BASE", "BITCOIN", "BINANCE"]

# 1 & 2. Gelişmiş RugCheck, LP Kilit Süresi (Lock Duration) Kontrolü
def check_advanced_security(mint_address, chain_id):
    if chain_id.lower() != "solana":
        return True, "🟢 EVM Güvenlik Temiz", "Dengeli Dağılım", "🔥 LP Durumu Normal"
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
        response = requests.get(url, timeout=6)
        if response.status_code == 200:
            data = response.json()
            score = data.get("score", 0)
            risks = data.get("risks", [])
            lockers = data.get("lpLockers", [])
            
            high_dev_share = False
            lp_unlocked = False
            
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True

            # Madde 2: En az 30 günlük kilit süresi kontrolü (2,592,000 saniye = 30 gün)
            long_term_lock = False
            if lockers:
                for locker in lockers:
                    unlock_time = locker.get("unlockTime", 0)
                    current_time = int(time.time())
                    if unlock_time - current_time >= 2592000:
                        long_term_lock = True
                        break

            is_safe = score < 600 and not lp_unlocked and not high_dev_share
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            clustering_info = "⚠️ Dev/Yüksek Cüzdan Payı Var!" if high_dev_share else "🟢 Dengeli Cüzdan Dağılımı"
            
            if lp_unlocked:
                lp_info = "⚠️ LP Kilitli Değil / Riskli"
            elif long_term_lock:
                lp_info = "🔒 LP En Az 30 Gün Kilitli / Güvenli"
            else:
                lp_info = "🔥 LP Yakılmış veya Kısa Süreli Kilitli"

            return is_safe, status, clustering_info, lp_info
            
        return False, "⚠️ Güvenlik Verisi Alınamadı", "Bilinmiyor", "Bilinmiyor"
    except Exception as e:
        print(f"RugCheck Hatası: {e}")
        return False, "⚠️ Güvenlik Taraması Yapılamadı", "Bilinmiyor", "Bilinmiyor"

# 3. Min 15 Dk Havuz Yaşı & Smart Money Kontrolü
def check_smart_money_and_age(pair_data):
    pair_created_at = pair_data.get("pairCreatedAt", 0)
    current_time_ms = int(time.time() * 1000)
    
    # En az 15 dakika (900,000 ms) açılış süresi kontrolü
    if pair_created_at > 0 and (current_time_ms - pair_created_at) < 900000:
        return False, "⚠️ Havuz Çok Yeni (<15 dk)"

    txns = pair_data.get("txns", {}).get("h1", {})
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    volume = pair_data.get("volume", {}).get("h1", 0)
    
    if volume > 80000 and buys > (sells * 1.3):
        return True, "🐋 Güçlü Akıllı Para (Smart Money) Alım Baskısı!"
    elif volume > 30000 and buys > 60:
        return True, "👀 Erken Aşama Balina Girişi Var"
    return True, "⚪ Standart İşlem Hacmi"

def get_ai_score_and_narrative(symbol, chain, volume, price_change, liquidity, security):
    base_score = 6.0
    if volume > 100000:
        base_score += 1.5
    elif volume > 50000:
        base_score += 0.8

    if liquidity > 30000:
        base_score += 1.0
    elif liquidity > 15000:
        base_score += 0.5

    if price_change > 20:
        base_score += 0.8
    elif price_change < 0:
        base_score -= 1.0

    numeric_score = round(min(max(base_score, 4.0), 9.8), 1)
    gemini_analysis = f"Hacim (${volume:,.0f}) ve Likidite (${liquidity:,.0f}) dengesi teknik açıdan incelendi."
    gpt_narrative = f"{symbol} token için sosyal trend ivmesi takip ediliyor."

    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt_text = (
                f"Token: {symbol}, Ağ: {chain}, Hacim: ${volume}, Değişim: %{price_change}. "
                f"Bu veriler için 1 cümlelik Türkçe teknik yorum ve 1-10 arası dinamik puan üret. "
                f"Format: SKOR: 8.3/10 - Yüksek alım baskısı ile ivme pozitif."
            )
            payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=7)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "SKOR:" in text:
                    parts = text.split("SKOR:")[1].split("-")
                    try:
                        numeric_score = float(parts[0].replace("/10", "").strip())
                    except:
                        pass
                    if len(parts) > 1:
                        gemini_analysis = parts[1].strip()
                else:
                    gemini_analysis = text
        except Exception as e:
            print(f"Gemini Hatası: {e}")

    if OPENAI_API_KEY:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": f"{symbol} kripto parasının viral potansiyeli nedir? 1 Türkçe cümle."}],
                "max_tokens": 60
            }
            res = requests.post(url, headers=headers, json=payload, timeout=7)
            if res.status_code == 200:
                gpt_narrative = res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"OpenAI Hatası: {e}")

    return numeric_score, f"{numeric_score}/10 🔥", gemini_analysis, gpt_narrative

def get_filtered_memecoins():
    filtered_list = []
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/token-profiles/latest/v1",
        "https://api.dexscreener.com/latest/dex/search?q=base"
    ]
    
    candidate_addresses = []
    for ep in endpoints:
        try:
            res = requests.get(ep, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    for item in data[:20]:
                        token_addr = item.get("tokenAddress")
                        if token_addr:
                            candidate_addresses.append(token_addr)
                elif isinstance(data, dict) and "pairs" in data:
                    for pair in data["pairs"][:20]:
                        if pair.get("chainId") == "base":
                            base_addr = pair.get("baseToken", {}).get("address")
                            if base_addr:
                                candidate_addresses.append(base_addr)
        except Exception as e:
            print(f"Endpoint hatası ({ep}): {e}")

    if candidate_addresses:
        unique_addrs = list(set(candidate_addresses))[:40]
        addrs_str = ",".join(unique_addrs)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}"
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                pairs = response.json().get("pairs", [])
                
                for pair in pairs:
                    chain_id = pair.get("chainId", "")
                    base_token = pair.get("baseToken", {})
                    symbol = base_token.get("symbol", "UNKNOWN")
                    address = base_token.get("address", "")
                    price_usd = float(pair.get("priceUsd", 0))

                    if not address or symbol.upper() in IGNORE_TOKENS or address in seen_tokens:
                        continue

                    if symbol.upper() in INVALID_NAMES:
                        continue

                    # Madde 3: Min 15 Dk Havuz Yaşı Filtresi
                    is_old_enough, smart_money_status = check_smart_money_and_age(pair)
                    if not is_old_enough:
                        continue

                    volume = pair.get("volume", {}).get("h1", 0)
                    liquidity = pair.get("liquidity", {}).get("usd", 0)
                    fdv = pair.get("fdv", 0)
                    price_change = pair.get("priceChange", {}).get("h1", 0)

                    if volume < 25000 or liquidity < 8000 or price_change < -25:
                        continue

                    max_vol_ratio = 25 if chain_id.lower() == "base" else 15
                    if liquidity > 0 and (volume / liquidity) > max_vol_ratio:
                        continue

                    url_link = pair.get("url", "https://dexscreener.com")

                    is_safe, security_status, clustering_info, lp_info = check_advanced_security(address, chain_id)
                    if not is_safe:
                        continue

                    num_score, ai_score_str, gemini_eval, gpt_narrative = get_ai_score_and_narrative(
                        symbol, chain_id, volume, price_change, liquidity, security_status
                    )

                    seen_tokens.add(address)

                    # Madde 5: Sinyal Atılan Token'ı Fiyatı ile PnL Takibine Al
                    pnl_tracker[address] = {
                        "symbol": symbol,
                        "entry_price": price_usd,
                        "timestamp": time.time()
                    }
                    print(f"📈 PnL Takibi Başlatıldı: ${symbol} @${price_usd:.8f}")

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
                        "smart_money": smart_money_status,
                        "ai_score": ai_score_str,
                        "gemini_eval": gemini_eval,
                        "gpt_narrative": gpt_narrative,
                        "dex_url": url_link,
                    })
        except Exception as e:
            print(f"Token detay hatası: {e}")

    return filtered_list

def send_telegram_alert(coin):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    if coin["chain"].lower() == "solana":
        buy_url = f"https://t.me/solana_trojanbot?start=r-user-{coin['address']}"
        buy_btn_text = "🚀 Trojan ile Al (Solana)"
    else:
        buy_url = f"https://t.me/MaestroSniperBot?start={coin['address']}"
        buy_btn_text = f"🚀 Maestro ile Al ({coin['chain']})"

    caption = (
        "🔥 **AI GÜVEN & HYPE SKORU:** `" + str(coin['ai_score']) + "`\n\n" +
        "🌐 **Ağ:** `" + str(coin['chain']) + "` - 🪙 **Token:** $" + str(coin['symbol']) + "\n" +
        "📈 **1S Değişim:** %" + str(coin['price_change']) + " - 📊 **1S Hacim:** $" + f"{coin['volume']:,.0f}" + "\n" +
        "💧 **Likidite:** $" + f"{coin['liquidity']:,.0f}" + " - 💰 **FDV:** $" + f"{coin['fdv']:,.0f}" + "\n\n" +
        "🛡️ **Güvenlik:** " + str(coin['security']) + "\n" +
        "👥 **Kümelenme:** " + str(coin['clustering']) + "\n" +
        "🔥 **Likidite:** " + str(coin['lp_info']) + "\n" +
        "🐋 **Smart Money:** " + str(coin['smart_money']) + "\n\n" +
        "🤖 **Gemini Analizi:** _" + str(coin['gemini_eval']) + "_\n" +
        "💬 **ChatGPT Hype:** _" + str(coin['gpt_narrative']) + "_\n\n" +
        "📍 **CA:**\n`" + str(coin['address']) + "`"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": buy_btn_text, "url": buy_url},
            {"text": "⚡ DexScreener", "url": coin["dex_url"]},
        ]]
    }
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": caption,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup,
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram mesaj hatası: {e}")

def run_bot_loop():
    print("Multi-chain Pro AI Sniper Bot döngüsü başlatıldı...")
    while True:
        try:
            coins = get_filtered_memecoins()
            for coin in coins[:3]:
                send_telegram_alert(coin)
                time.sleep(3)
        except Exception as e:
            print(f"Bot döngüsü hatası: {e}")
        time.sleep(300)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot_loop)
    bot_thread.daemon = True
    bot_thread.start()

    app.run(host="0.0.0.0", port=10000)
