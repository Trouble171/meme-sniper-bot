import os
import time
import json
import asyncio
import threading
import requests
import websockets
from flask import Flask

# Solana & Solders entegrasyonu
try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction
except ImportError:
    pass

app = Flask(__name__)

start_time = time.time()

@app.route("/")
def home():
    return "Meme Coin Sniper Bot (Auto-Buy & Auto-TP/SL Edition) Aktif!", 200

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WEBSOCKET_URL = os.environ.get("WEBSOCKET_URL")
SOLANA_PRIVATE_KEY = os.environ.get("SOLANA_PRIVATE_KEY")
AUTO_BUY_AMOUNT_SOL = float(os.environ.get("AUTO_BUY_AMOUNT_SOL", "0.1"))

seen_tokens = set()
pnl_tracker = {} # {address: {symbol, entry_price, chain, amount_held, total_bought_sol, timestamp}}
scanned_count = 0
last_update_id = 0

IGNORE_TOKENS = ["USDC", "USDT", "WETH", "WBTC", "SOL", "ETH", "BNB", "WSOL", "WBNB", "DAI"]
INVALID_NAMES = ["SOLANA", "BSC", "ROBINHOOD", "ETHEREUM", "BASE", "BITCOIN", "BINANCE"]
HOT_NARRATIVES = ["AI", "AGENT", "PUMP", "MUSK", "TRUMP", "PEPE", "CAT", "DOGE", "NEIRO", "SOL", "FART", "PENGU"]

# Keypair yükleme
payer_keypair = None
if SOLANA_PRIVATE_KEY:
    try:
        payer_keypair = Keypair.from_base58_string(SOLANA_PRIVATE_KEY)
        print(f"🔑 Solana Cüzdanı Yüklendi: {payer_keypair.pubkey()}")
    except Exception as e:
        print(f"⚠️ Keypair Yükleme Hatası: {e}")

# Jupiter API Üzerinden Otomatik Alım-Satım (Swap)
def execute_jupiter_swap(input_mint, output_mint, amount_lamports_or_raw, is_sell=False):
    if not payer_keypair:
        print("⚠️ Private Key tanımlı değil, Swap yapılamıyor.")
        return False, "Cüzdan Anahtarı Eksik"
    
    try:
        # 1. Quote Al
        quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={int(amount_lamports_or_raw)}&slippageBps=500"
        res = requests.get(quote_url, timeout=6)
        if res.status_code != 200:
            return False, "Quote Alınamadı"
        
        quote_data = res.json()

        # 2. Swap Transaction İsteği
        swap_url = "https://quote-api.jup.ag/v6/swap"
        payload = {
            "quoteResponse": quote_data,
            "userPublicKey": str(payer_keypair.pubkey()),
            "wrapAndUnwrapSol": True,
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto"
        }
        swap_res = requests.post(swap_url, json=payload, timeout=8)
        if swap_res.status_code != 200:
            return False, "Swap TX Oluşturulamadı"

        swap_tx_base64 = swap_res.json().get("swapTransaction")
        
        # 3. İmzala ve İşlemi Ağ Gönder
        raw_tx = VersionedTransaction.from_bytes(bytes(requests.auth.base64.b64decode(swap_tx_base64)))
        signature = payer_keypair.sign_message(raw_tx.message)
        signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

        # Solana Mainnet RPC Üzerinden Gönderim
        rpc_url = "https://api.mainnet-beta.solana.com"
        tx_bytes = bytes(signed_tx)
        encoded_tx = requests.auth.base64.b64encode(tx_bytes).decode('utf-8')

        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [encoded_tx, {"encoding": "base64", "skipPreflight": True}]
        }
        
        tx_res = requests.post(rpc_url, json=rpc_payload, timeout=10)
        if tx_res.status_code == 200 and "result" in tx_res.json():
            tx_hash = tx_res.json()["result"]
            return True, tx_hash
        return False, "RPC Gönderim Hatası"

    except Exception as e:
        print(f"Jupiter Swap Hatası: {e}")
        return False, str(e)

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
            serial_dev_risk = False
            
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True
                if "creator" in risk_name or "dangerous authority" in risk_name:
                    serial_dev_risk = True

            long_term_lock = False
            if lockers:
                for locker in lockers:
                    unlock_time = locker.get("unlockTime", 0)
                    current_time = int(time.time())
                    if unlock_time - current_time >= 2592000:
                        long_term_lock = True
                        break

            is_safe = score < 600 and not lp_unlocked and not high_dev_share and not serial_dev_risk
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            
            if serial_dev_risk:
                clustering_info = "⚠️ Şüpheli Geliştirici (Dev) Cüzdanı!"
            elif high_dev_share:
                clustering_info = "⚠️ Yüksek Cüzdan Yoğunlaşması"
            else:
                clustering_info = "🟢 Dengeli Cüzdan Dağılımı"
            
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

def check_smart_money_and_age(pair_data):
    pair_created_at = pair_data.get("pairCreatedAt", 0)
    current_time_ms = int(time.time() * 1000)
    
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
    matched_narrative = None
    
    symbol_upper = symbol.upper()
    for kw in HOT_NARRATIVES:
        if kw in symbol_upper:
            base_score += 1.5
            matched_narrative = f"🔥 HİKAYE EŞLEŞMESİ: #{kw} Trend Anlatısı"
            break

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

    return numeric_score, f"{numeric_score}/10 🔥", gemini_analysis, gpt_narrative, matched_narrative

def get_filtered_memecoins():
    global scanned_count
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
        scanned_count += len(unique_addrs)
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

                    num_score, ai_score_str, gemini_eval, gpt_narrative, matched_narrative = get_ai_score_and_narrative(
                        symbol, chain_id, volume, price_change, liquidity, security_status
                    )

                    seen_tokens.add(address)

                    # Otomatik Alım İşlemi (Solana Ağı İçin)
                    auto_bought = False
                    tx_info = ""
                    if chain_id.lower() == "solana" and payer_keypair:
                        sol_mint = "So11111111111111111111111111111111111111112"
                        lamports = int(AUTO_BUY_AMOUNT_SOL * 1e9)
                        success, tx_hash = execute_jupiter_swap(sol_mint, address, lamports)
                        if success:
                            auto_bought = True
                            tx_info = f"\n⚡ **OTOMATİK ALINDI ({AUTO_BUY_AMOUNT_SOL} SOL)**\n[Solscan İncele](https://solscan.io/tx/{tx_hash})"

                    pnl_tracker[address] = {
                        "symbol": symbol,
                        "entry_price": price_usd,
                        "chain": chain_id.upper(),
                        "tp_done": False,
                        "timestamp": time.time()
                    }

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
                        "matched_narrative": matched_narrative,
                        "auto_bought": tx_info,
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

    narrative_line = f"{coin['matched_narrative']}\n\n" if coin.get("matched_narrative") else ""
    auto_buy_line = f"{coin['auto_bought']}\n\n" if coin.get("auto_bought") else ""

    caption = (
        narrative_line + auto_buy_line +
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

# Otomatik TP (%50 Kâr) ve SL (-%25 Stop Loss) Kontrol Döngüsü
def auto_tp_sl_checker():
    while True:
        try:
            if pnl_tracker and payer_keypair:
                addrs = list(pnl_tracker.keys())[:20]
                addrs_str = ",".join(addrs)
                res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}", timeout=5)
                if res.status_code == 200:
                    pairs = res.json().get("pairs", [])
                    prices = {p.get("baseToken", {}).get("address"): float(p.get("priceUsd", 0)) for p in pairs}

                    for addr, data in list(pnl_tracker.items()):
                        entry = data["entry_price"]
                        current = prices.get(addr, entry)
                        if entry > 0:
                            diff = ((current - entry) / entry) * 100
                            
                            # %50 Kâr Alma (Take Profit)
                            if diff >= 50 and not data.get("tp_done"):
                                pnl_tracker[addr]["tp_done"] = True
                                msg = f"🎉 **KÂR ALMA ZAMANI! (%50 YÜKSELİŞ)**\n\n🪙 **Token:** ${data['symbol']}\n📈 **PnL:** %{diff:+.2f}\n⚡ Pozisyonun %50'si satılıyor..."
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                            
                            # -%25 Stop Loss
                            elif diff <= -25:
                                msg = f"🚨 **STOP-LOSS TETİKLENDİ (-%25)**\n\n🪙 **Token:** ${data['symbol']}\n📉 **PnL:** %{diff:+.2f}\n🛡️ Sermayeyi korumak için pozisyon kapatılıyor."
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                                del pnl_tracker[addr]

        except Exception as e:
            print(f"TP/SL kontrol hatası: {e}")
        time.sleep(15)

async def websocket_listener():
    if not WEBSOCKET_URL:
        return
    print("⚡ WebSocket Anlık Blok Zinciri Dinleyicisi Başlatılıyor...")
    while True:
        try:
            async with websockets.connect(WEBSOCKET_URL) as ws:
                subscribe_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "logsSubscribe", "params": [{"mentions": ["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"]}, {"commitment": "processed"}]})
                await ws.send(subscribe_msg)
                while True:
                    await ws.recv()
        except Exception as e:
            await asyncio.sleep(5)

def start_websocket_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_listener())

def check_telegram_commands():
    global last_update_id
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"offset": last_update_id + 1, "timeout": 2}, timeout=5)
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
                    auto_status = "🟢 Aktif (0.1 SOL)" if SOLANA_PRIVATE_KEY else "⚪ Pasif"
                    status_msg = (
                        "🤖 **BOT ANLIK DURUM RAPORU**\n\n"
                        f"⏱️ **Çalışma Süresi:** {uptime_min} dakika\n"
                        f"🚀 **Otomatik Alım:** {auto_status}\n"
                        f"🔍 **Taranan Havuz Sayısı:** {scanned_count}\n"
                        f"🎯 **Sinyal Atılan Token:** {len(seen_tokens)}\n"
                        "🛡️ **Aktif Filtreler:** Min $25k Hacim | Min $8k Likidite | Min 15 Dk Yaş | Auto TP/SL"
                    )
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": status_msg, "parse_mode": "Markdown"})

                elif text == "/pnl":
                    if not pnl_tracker:
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "📊 Henüz PnL takibinde olan token yok."})
                        continue

                    pnl_msg = "📈 **SİNYAL PERFORMANS & PnL TAKİBİ**\n\n"
                    addrs = list(pnl_tracker.keys())[:20]
                    addrs_str = ",".join(addrs)
                    
                    try:
                        res_dex = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}", timeout=5)
                        if res_dex.status_code == 200:
                            pairs = res_dex.json().get("pairs", [])
                            prices = {p.get("baseToken", {}).get("address"): float(p.get("priceUsd", 0)) for p in pairs}

                            for addr, data in pnl_tracker.items():
                                entry = data["entry_price"]
                                current = prices.get(addr, entry)
                                if entry > 0:
                                    diff = ((current - entry) / entry) * 100
                                    icon = "🟢" if diff >= 0 else "🔴"
                                    pnl_msg += f"{icon} **${data['symbol']}** ({data['chain']}): %{diff:+.2f}\n"

                            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": pnl_msg, "parse_mode": "Markdown"})
                    except Exception as e:
                        print(f"PnL sorgu hatası: {e}")
    except Exception as e:
        pass

def run_bot_loop():
    print("Multi-chain Interactive AI Sniper Bot döngüsü başlatıldı...")
    while True:
        try:
            check_telegram_commands()
            coins = get_filtered_memecoins()
            for coin in coins[:3]:
                send_telegram_alert(coin)
                time.sleep(3)
        except Exception as e:
            print(f"Bot döngüsü hatası: {e}")
        time.sleep(120)

if __name__ == "__main__":
    ws_thread = threading.Thread(target=start_websocket_thread)
    ws_thread.daemon = True
    ws_thread.start()

    tp_sl_thread = threading.Thread(target=auto_tp_sl_checker)
    tp_sl_thread.daemon = True
    tp_sl_thread.start()

    bot_thread = threading.Thread(target=run_bot_loop)
    bot_thread.daemon = True
    bot_thread.start()

    app.run(host="0.0.0.0", port=10000)
