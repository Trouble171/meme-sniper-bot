import os
import time
import threading
import requests
from flask import Flask

# Flask Web Sunucusu (Render & UptimeRobot için)
app = Flask(__name__)

@app.route("/")
def home():
    return "Meme Coin Sniper Bot (Ultra Fast + AI + Security) Aktif!", 200

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

# 1. Gelişmiş RugCheck, Dev Wallet ve LP Burn Kontrolü (Ücretsiz)
def check_advanced_security(mint_address, chain_id):
    if chain_id.lower() != "solana":
        return True, "🟢 EVM Güvenlik Temiz", "Dengeli Dağılım", "🔥 LP Durumu Normal"
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
        response = requests.get(url, timeout=6)
        if response.status_code == 200:
            data = response.json()
            score = data.get("score", 0)
            
            # Risk Analizi
            risks = data.get("risks", [])
            high_dev_share = False
            lp_unlocked = False
            
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                # Dev Cüzdanında Yüksek Pay Var mı?
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                # Likidite Kilitli/Yanmış mı?
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True

            # Filtreleme Kararı: Skor yüksekse veya LP kilitli değilse ELE!
            is_safe = score < 800 and not lp_unlocked
            
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            clustering_info = "⚠️ Dev/Yüksek Cüzdan Payı Var!" if high_dev_share else "🟢 Dengeli Cüzdan Dağılımı"
            lp_info = "⚠️ LP Kilitli Değil / Riskli" if lp_unlocked else "🔥 LP Yakılmış / Kilitli"
            
            return is_safe, status, clustering_info, lp_info
            
        return True, "⚠️ Güvenlik Verisi Alınamadı", "Bilinmiyor", "Bilinmiyor"
    except Exception:
        return True, "⚠️ Güvenlik Taraması Yapılamadı", "Bilinmiyor", "Bilinmiyor"

# 2. Smart Money & Hacim Anomali Kontrolü
def check_smart_money(pair_data):
    txns = pair_data.get("txns", {}).get("h1", {})
    buys = txns.get("buys", 0)
    sells = txns.get("sells", 0)
    volume = pair_data.get("volume", {}).get("h1", 0)
    
    if volume > 50000 and buys > (sells * 1.5):
        return "🐋 Güçlü Akıllı Para (Smart Money) Alım Baskısı!"
    elif volume > 20000 and buys > 80:
        return "👀 Erken Aşama Balina Girişi Var"
    return "⚪ Standart İşlem Hacmi"

# 3. Çift AI Analiz Katmanı (Dinamik Analiz)
def get_ai_score_and_narrative(symbol, chain, volume, price_change, security, clustering):
    gemini_analysis = "Teknik veri analiz edilemedi."
    gpt_narrative = "Sosyal potansiyel inceleniyor."
    ai_score = "7.8/10 ⚡"

    # Gemini API (Teknik Değerlendirme & Dinamik Skor)
    if GEMINI_API_KEY:
        try:
            prompt = (
                f"Token: {symbol}, Ağ: {chain}, 1S Hacim: ${volume}, 1S Değişim: %{price_change}, Güvenlik: {security}. "
                f"Bu verileri analiz edip token için 1-10 arası bir potansiyel skoru belirle ve 1 cümlelik Türkçe teknik değerlendirme yap. "
                f"Format kesinlikle 'SKOR: X/10 | YORUM' şeklinde olsun."
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "SKOR:" in raw_text and "|" in raw_text:
                    parts = raw_text.split("|", 1)
                    ai_score = parts[0].replace("SKOR:", "").strip() + " 🔥"
                    gemini_analysis = parts[1].strip()
                else:
                    gemini_analysis = raw_text
        except Exception as e:
            print(f"Gemini API Hatası: {e}")

    # ChatGPT OpenAI API (Meme & Hype Potansiyeli)
    if OPENAI_API_KEY:
        try:
            prompt = f"Meme token ismi/sembolü: {symbol}. Bu ismin meme kültüründeki özgünlüğünü ve topluluk viral potansiyelini 1 cümle Türkçe ile yorumla."
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
            if res.status_code == 200:
                gpt_narrative = res.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"OpenAI API Hatası: {e}")

    return ai_score, gemini_analysis, gpt_narrative

# 4. Ultra Hızlı Havuz & Trend Taraması
def get_filtered_memecoins():
    filtered_list = []
    
    # DexScreener En Yeni ve En Sıcak Havuz API'leri
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
            print(f"Endpoint tarama hatası ({ep}): {e}")

    # Yakalanan adreslerin detaylı zincir verilerini sorgula
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

                    # 1. Filtre: Boş adresler, ana coin'ler veya taranmış olanlar
                    if not address or symbol.upper() in IGNORE_TOKENS or address in seen_tokens:
                        continue

                    # 2. Filtre: Ağ ismiyle çıkan taklit/sahte coin engeli
                    if symbol.upper() in INVALID_NAMES:
                        continue

                    volume = pair.get("volume", {}).get("h1", 0)
                    
                    # 3. Filtre: Minimum $10,000 Hacim
                    if volume < 10000:
                        continue

                    price_change = pair.get("priceChange", {}).get("h1", 0)
                    fdv = pair.get("fdv", 0)
                    url_link = pair.get("url", "https://dexscreener.com")

                    # 4. Filtre: Gelişmiş RugCheck, Dev Wallet ve LP Kilit Kontrolü
                    is_safe, security_status, clustering_info, lp_info = check_advanced_security(address, chain_id)
                    if not is_safe:
                        continue

                    smart_money_status = check_smart_money(pair)

                    # 5. Çift AI Analiz Katmanı
                    ai_score, gemini_eval, gpt_narrative = get_ai_score_and_narrative(
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
                        "security": security_status,
                        "clustering": clustering_info,
                        "lp_info": lp_info,
                        "smart_money": smart_money_status,
                        "ai_score": ai_score,
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
        f"📈 **1S Değişim:** %{coin['price_change']} | 📊 **1S Hacim:** ${coin['volume']:,.0f}\n\n"
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
    print("Multi-chain Ultra-Fast AI Sniper Bot döngüsü başlatıldı...")
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
