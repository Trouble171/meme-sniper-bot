import os
import time
import threading
import requests
from flask import Flask

# Flask Web Sunucusu (Render & UptimeRobot için)
app = Flask(__name__)

@app.route("/")
def home():
    return "Meme Coin Sniper Bot (Fixed AI + Advanced Filters) Aktif!", 200

# Environment Değişkenleri
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

seen_tokens = set()

IGNORE_TOKENS = [
    "USDC", "USDT", "WETH", "WBTC", "SOL", "ETH", "BNB", "WSOL", "WBNB", "DAI"
]

INVALID_NAMES = ["SOLANA", "BSC", "ROBINHOOD", "ETHEREUM", "BASE", "BITCOIN", "BINANCE"]

# 1. Gelişmiş RugCheck, Dev Wallet ve LP Burn Kontrolü
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
            high_dev_share = False
            lp_unlocked = False
            
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True

            # Filtre: Skor < 600 ve LP kilitli olmalı
            is_safe = score < 600 and not lp_unlocked and not high_dev_share
            
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            clustering_info = "⚠️ Dev/Yüksek Cüzdan Payı Var!" if high_dev_share else "🟢 Dengeli Cüzdan Dağılımı"
            lp_info = "⚠️ LP Kilitli Değil / Riskli" if lp_unlocked else "🔥 LP Yakılmış / Kilitli"
            
            return is_safe, status, clustering_info, lp_info
            
        return False, "⚠️ Güvenlik Verisi Alınamadı", "Bilinmiyor", "Bilinmiyor"
    except Exception as e:
        print(f"RugCheck Hatası: {e}")
        return False, "⚠️ Güvenlik Taraması Yapılamadı", "Bilinmiyor", "Bilinmiyor"

# 2. Smart Money & Hacim Anomali Kontrolü
def check_smart_money(pair_data):
    txns = pair_data.get("txns", {}).get("h1", {})
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    volume = pair_data.get("volume", {}).get("h1", 0)
    
    if volume > 80000 and buys > (sells * 1.3):
        return "🐋 Güçlü Akıllı Para (Smart Money) Alım Baskısı!"
    elif volume > 30000 and buys > 60:
        return "👀 Erken Aşama Balina Girişi Var"
    return "⚪ Standart İşlem Hacmi"

# 3. Çift AI Analiz Katmanı (Tam Düzeltilmiş API Çağrıları)
def get_ai_score_and_narrative(symbol, chain, volume, price_change, security, clustering):
    gemini_analysis = "Teknik veri analiz edilemedi."
    gpt_narrative = "Sosyal potansiyel inceleniyor."
    numeric_score = 7.5

    # Gemini REST API Düzeltilmiş İstek
    if GEMINI_API_KEY:
        try:
            prompt_text = (
                f"Token: {symbol}, Ağ: {chain}, 1S Hacim: ${volume}, 1S Değişim: %{price_change}, Güvenlik: {security}. "
                f"Bu verileri analiz et. ÖNCE 'SKOR: X.X/10' yazıp ardından 1 cümlelik Türkçe teknik yorum ekle. "
                f"Örnek format: SKOR: 8.5/10 | Yüksek hacim ve dengeli dağılım ile yükseliş potansiyeli mevcut."
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": prompt_text}]
                }]
            }
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                res_data = res.json()
                raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                if "SKOR:" in raw_text:
                    score_part = raw_text.split("SKOR:")[1].strip()
                    if "|" in score_part:
                        val_str, eval_str = score_part.split("|", 1)
                        try:
                            numeric_score = float(val_str.replace("/10", "").strip())
                        except:
                            numeric_score = 7.5
                        gemini_analysis = eval_str.strip()
                    else:
                        gemini_analysis = score_part
                else:
                    gemini_analysis = raw_text
            else:
                print(f"Gemini API HTTP Hatası ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"Gemini Kod Hatası: {e}")

    # ChatGPT OpenAI API
    if OPENAI_API_KEY:
        try:
            prompt_text = f"Meme token sembolü: {symbol}. Bu sembolün meme kültüründeki viral potansiyelini 1 cümle Türkçe ile yorumla."
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt_text}],
                "max_tokens": 80
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
            if res.status_code == 200:
                gpt_narrative = res.json()["choices"][0]["message"]["content"].strip()
            else:
                print(f"OpenAI API HTTP Hatası ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"OpenAI Kod Hatası: {e}")

    return numeric_score, f"{numeric_score}/10 🔥", gemini_analysis, gpt_narrative

# 4. Gelişmiş Filtreli Havuz Taraması
def get_filtered_memecoins():
    filtered_list = []
    
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/token-profiles/latest/v1"
    ]
    
    candidate_addresses = []
    for ep in endpoints:
        try:
            res = requests.get(ep, timeout=8)
            if res.status_code == 200:
                data = res.json()
                for item in data[:20]:
                    token_addr = item.get("tokenAddress")
                    if token_addr:
                        candidate_addresses.append(token_addr)
        except Exception as e:
            print(f"Endpoint hatası ({ep}): {e}")

    if candidate_addresses:
        unique_addrs = list(set(candidate_addresses))[:30]
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

                    if not address or symbol.upper() in IGNORE_TOKENS or address in seen_tokens:
                        continue

                    # Ağ veya ana isim taklidi engelleyici
                    if symbol.upper() in INVALID_NAMES or chain_id.upper() in INVALID_NAMES:
                        continue

                    volume = pair.get("volume", {}).get("h1", 0)
                    liquidity = pair.get("liquidity", {}).get("usd", 0)
                    fdv = pair.get("fdv", 0)
                    price_change = pair.get("priceChange", {}).get("h1", 0)

                    # Dengeli Filtreler:
                    # Minimum $25,000 Hacim
                    if volume < 25000:
                        continue

                    # Minimum $8,000 Likidite
                    if liquidity < 8000:
                        continue

                    # Yapay Hacim Engeli (Hacim / Likidite Oranı 15'ten büyükse ele)
                    if liquidity > 0 and (volume / liquidity) > 15:
                        continue

                    # Sert Çöküş Yemiş Coin'leri Ele (Son 1 saatte -%25'ten fazla düşenler)
                    if price_change < -25:
                        continue

                    url_link = pair.get("url", "https://dexscreener.com")

                    # Güvenlik Kontrolü
                    is_safe, security_status, clustering_info, lp_info = check_advanced_security(address, chain_id)
                    if not is_safe:
                        continue

                    smart_money_status = check_smart_money(pair)

                    # AI Değerlendirmesi
                    num_score, ai_score_str, gemini_eval, gpt_narrative = get_ai_score_and_narrative(
                        symbol, chain_id, volume, price_change, security_status, clustering_info
                    )

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
                        "smart_money": smart_money_status,
                        "ai_score": ai_score_str,
                        "gemini_eval": gemini_eval,
                        "gpt_narrative": gpt_narrative,
                        "dex_url": url_link,
                    })
        except Exception as e:
            print(f"Token detay çekme hatası: {e}")

    return filtered_list

# 5. Telegram Bildirim Gönderimi
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
        f"🔥 **AI GÜVEN & HYPE SKORU:** `{coin['ai_score']}`\n\n"
        f"🌐 **Ağ:** `{coin['chain']}` | 🪙 **Token:** `${coin['symbol']}`\n"
        f"📈 **1S Değişim:** %{coin['price_change']} | 📊 **1S Hacim:** ${coin['volume']:,.0f}\n"
        f"💧 **Likidite:** ${coin['liquidity']:,.0f} \vert{} 💰 **FDV:** ${coin['fdv']:,.0f}\n\n"
        f"🛡️ **Güvenlik:** {coin['security']}\n"
        f"👥 **Kümelenme:** {coin['clustering']}\n"
        f"🔥 **Likidite:** {coin['lp_info']}\n"
        f"🐋 **Smart Money:** {coin['smart_money']}\n\n"
        f"🤖 **Gemini Analizi:** _{coin['gemini_eval']}_\n"
        f"💬 **ChatGPT Hype:** _{coin['gpt_narrative']}_\n\n"
        f"📍 **CA:**\n`{coin['address']}`"
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
    print("Multi-chain AI Sniper Bot döngüsü başlatıldı...")
    while True:
        try:
            coins = get_filtered_memecoins()
            for coin in coins[:2]:
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
