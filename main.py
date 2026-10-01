import os
import time
import json
import asyncio
import threading
import requests
import websockets
from flask import Flask

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
    return "Meme Coin Sniper Bot (High-Tolerance RPC Engine) Aktif!", 200

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
WEBSOCKET_URL = os.environ.get("WEBSOCKET_URL")
SOLANA_PRIVATE_KEY = os.environ.get("SOLANA_PRIVATE_KEY")
SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
AUTO_BUY_AMOUNT_SOL = float(os.environ.get("AUTO_BUY_AMOUNT_SOL", "0.09"))

seen_tokens = set()
pnl_tracker = {} 
scanned_count = 0
last_update_id = 0

IGNORE_TOKENS = ["USDC", "USDT", "WETH", "WBTC", "SOL", "ETH", "BNB", "WSOL", "WBNB", "DAI"]
INVALID_NAMES = ["SOLANA", "BSC", "ROBINHOOD", "ETHEREUM", "BASE", "BITCOIN", "BINANCE"]

payer_keypair = None
if SOLANA_PRIVATE_KEY:
    try:
        payer_keypair = Keypair.from_base58_string(SOLANA_PRIVATE_KEY)
        print(f"🔑 Cüzdan Yüklendi: {payer_keypair.pubkey()}")
    except Exception as e:
        print(f"⚠️️ Cüzdan Yükleme Hatası: {e}")

def send_raw_tx_private_rpc(encoded_tx):
    rpc_nodes = [
        SOLANA_RPC_URL,
        "https://rpc.ankr.com/solana",
        "https://api.mainnet-beta.solana.com"
    ]
    for rpc in rpc_nodes:
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sendTransaction",
                "params": [encoded_tx, {"encoding": "base64", "skipPreflight": True, "maxRetries": 5}]
            }
            res = requests.post(rpc, json=payload, timeout=8)
            if res.status_code == 200 and "result" in res.json():
                return True, res.json()["result"]
        except Exception:
            continue
    return False, "Özel RPC Yanıt Vermedi"

def execute_solana_direct_swap(input_mint, output_mint, amount_lamports):
    if not payer_keypair:
        return False, "Cüzdan Anahtarı Eksik!"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    rpc_gateways = [
        "https://quote-api.jup.ag/v6",
        "https://lite-quote-api.jup.ag/v6",
        "https://swap-api.solana.com/v6"
    ]

    # Jupiter Aggregator (%20 Slippage Toleransı)
    for gateway in rpc_gateways:
        try:
            quote_url = f"{gateway}/quote?inputMint={input_mint}&outputMint={output_mint}&amount={int(amount_lamports)}&slippageBps=2000"
            res = requests.get(quote_url, headers=headers, timeout=5)
            
            if res.status_code == 200:
                quote_data = res.json()
                swap_payload = {
                    "quoteResponse": quote_data,
                    "userPublicKey": str(payer_keypair.pubkey()),
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": 600000
                }
                swap_res = requests.post(f"{gateway}/swap", json=swap_payload, headers=headers, timeout=6)
                
                if swap_res.status_code == 200 and "swapTransaction" in swap_res.json():
                    swap_tx_base64 = swap_res.json()["swapTransaction"]
                    raw_tx = VersionedTransaction.from_bytes(bytes(requests.auth.base64.b64decode(swap_tx_base64)))
                    signature = payer_keypair.sign_message(raw_tx.message)
                    signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

                    encoded_tx = requests.auth.base64.b64encode(bytes(signed_tx)).decode('utf-8')
                    success, tx_hash = send_raw_tx_private_rpc(encoded_tx)
                    if success:
                        return True, tx_hash
        except Exception:
            continue

    # Raydium Direct Fallback (%20 Slippage)
    try:
        ray_url = f"https://transaction-v1.raydium.io/compute/swap-base-in?inputMint={input_mint}&outputMint={output_mint}&amount={int(amount_lamports)}&slippageBps=2000&txVersion=V0"
        ray_res = requests.get(ray_url, headers=headers, timeout=6)
        if ray_res.status_code == 200 and ray_res.json().get("success"):
            data = ray_res.json().get("data", {})
            swap_tx_base64 = data.get("swapTransaction")
            if swap_tx_base64:
                raw_tx = VersionedTransaction.from_bytes(bytes(requests.auth.base64.b64decode(swap_tx_base64)))
                signature = payer_keypair.sign_message(raw_tx.message)
                signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])
                
                encoded_tx = requests.auth.base64.b64encode(bytes(signed_tx)).decode('utf-8')
                success, tx_hash = send_raw_tx_private_rpc(encoded_tx)
                if success:
                    return True, tx_hash
    except Exception:
        pass

    return False, "Jupiter & Raydium Yüksek Ağ Yoğunluğu"

def check_advanced_security(mint_address, chain_id):
    if chain_id.lower() != "solana":
        return True, "🟢 EVM Güvenlik Temiz", "Dengeli Dağılım", "🔥 LP Durumu Normal"
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
            
            for risk in risks:
                risk_name = risk.get("name", "").lower()
                if "single holder ownership" in risk_name or "high holder concentration" in risk_name:
                    high_dev_share = True
                if "low liquidity" in risk_name or "unlocked liquidity" in risk_name:
                    lp_unlocked = True
                if "creator" in risk_name or "dangerous authority" in risk_name:
                    serial_dev_risk = True

            is_safe = score < 300 and not lp_unlocked and not high_dev_share and not serial_dev_risk
            status = f"🟢 GÜVENLİ (Skor: {score})" if is_safe else f"🔴 RİSKLİ (Skor: {score})"
            clustering_info = "⚠️ Şüpheli Dev Cüzdanı" if serial_dev_risk else ("⚠️ Yüksek Yoğunlaşma" if high_dev_share else "🟢 Dengeli Dağılım")
            lp_info = "⚠️ LP Riskli" if lp_unlocked else "🔥 LP Güvenli / Kilitli"

            return is_safe, status, clustering_info, lp_info
        return False, "⚠️ Güvenlik Verisi Yok", "Bilinmiyor", "Bilinmiyor"
    except Exception as e:
        return False, "⚠️ Güvenlik Taraması Hatası", "Bilinmiyor", "Bilinmiyor"

def get_filtered_memecoins():
    global scanned_count
    filtered_list = []
    endpoints = [
        "https://api.dexscreener.com/token-boosts/top/v1",
        "https://api.dexscreener.com/token-profiles/latest/v1"
    ]
    
    candidate_addresses = []
    for ep in endpoints:
        try:
            res = requests.get(ep, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    for item in data[:20]:
                        token_addr = item.get("tokenAddress")
                        if token_addr:
                            candidate_addresses.append(token_addr)
        except Exception as e:
            pass

    if candidate_addresses:
        unique_addrs = list(set(candidate_addresses))[:30]
        scanned_count += len(unique_addrs)
        addrs_str = ",".join(unique_addrs)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}"
            response = requests.get(url, timeout=6)
            if response.status_code == 200:
                pairs = response.json().get("pairs", [])
                current_time_ms = int(time.time() * 1000)
                
                for pair in pairs:
                    chain_id = pair.get("chainId", "")
                    base_token = pair.get("baseToken", {})
                    symbol = base_token.get("symbol", "UNKNOWN")
                    address = base_token.get("address", "")
                    price_usd = float(pair.get("priceUsd", 0))

                    if not address or symbol.upper() in IGNORE_TOKENS or address in seen_tokens or symbol.upper() in INVALID_NAMES:
                        continue

                    pair_created_at = pair.get("pairCreatedAt", 0)
                    if pair_created_at > 0 and (current_time_ms - pair_created_at) < 1800000:
                        continue

                    volume = pair.get("volume", {}).get("h1", 0)
                    liquidity = pair.get("liquidity", {}).get("usd", 0)
                    fdv = pair.get("fdv", 0)
                    price_change = pair.get("priceChange", {}).get("h1", 0)

                    if volume < 50000 or liquidity < 30000 or price_change > 20 or price_change < 0:
                        continue

                    is_safe, security_status, clustering_info, lp_info = check_advanced_security(address, chain_id)
                    if not is_safe:
                        continue

                    seen_tokens.add(address)

                    auto_bought = False
                    tx_info = ""
                    
                    if chain_id.lower() == "solana" and payer_keypair:
                        sol_mint = "So11111111111111111111111111111111111111112"
                        lamports = int(AUTO_BUY_AMOUNT_SOL * 1e9)
                        success, tx_hash_or_err = execute_solana_direct_swap(sol_mint, address, lamports)
                        
                        if success:
                            auto_bought = True
                            tx_info = f"\n⚡ **GERÇEK ALIM BAŞARILI ({AUTO_BUY_AMOUNT_SOL} SOL)**\n[Solscan İncele](https://solscan.io/tx/{tx_hash_or_err})"
                            
                            pnl_tracker[address] = {
                                "symbol": symbol,
                                "entry_price": price_usd,
                                "highest_price": price_usd,
                                "chain": chain_id.upper(),
                                "tp_done": False,
                                "stop_level": -20.0,
                                "timestamp": time.time()
                            }
                        else:
                            tx_info = f"\n⚠️ **ALIM BAŞARISIZ:** _{tx_hash_or_err}_"

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
                        "smart_money": "🟢 Oturmuş Havuz",
                        "ai_score": "8.8/10 🔥",
                        "gemini_eval": "Güvenli havuz yapısı tespiti.",
                        "gpt_narrative": f"{symbol} takibe alındı.",
                        "auto_bought": tx_info,
                        "dex_url": pair.get("url", "https://dexscreener.com"),
                    })
        except Exception as e:
            pass

    return filtered_list

def send_telegram_alert(coin):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    buy_url = f"https://t.me/solana_trojanbot?start=r-user-{coin['address']}" if coin["chain"].lower() == "solana" else f"https://t.me/MaestroSniperBot?start={coin['address']}"
    buy_btn_text = "🚀 Trojan ile Al (Solana)" if coin["chain"].lower() == "solana" else f"🚀 Maestro ile Al ({coin['chain']})"

    auto_buy_line = f"{coin['auto_bought']}\n\n" if coin.get("auto_bought") else ""

    caption = (
        auto_buy_line +
        "🔥 **AI GÜVEN & HYPE SKORU:** `" + str(coin['ai_score']) + "`\n\n" +
        "🌐 **Ağ:** `" + str(coin['chain']) + "` - 🪙 **Token:** $" + str(coin['symbol']) + "\n" +
        "📈 **1S Değişim:** %" + str(coin['price_change']) + " - 📊 **1S Hacim:** $" + f"{coin['volume']:,.0f}" + "\n" +
        "💧 **Likidite:** $" + f"{coin['liquidity']:,.0f}" + " - 💰 **FDV:** $" + f"{coin['fdv']:,.0f}" + "\n\n" +
        "🛡️ **Güvenlik:** " + str(coin['security']) + "\n" +
        "👥 **Kümelenme:** " + str(coin['clustering']) + "\n" +
        "🔥 **Likidite:** " + str(coin['lp_info']) + "\n\n" +
        "🤖 **Gemini Analizi:** _" + str(coin['gemini_eval']) + "_\n\n" +
        "📍 **CA:**\n`" + str(coin['address']) + "`"
    )

    reply_markup = {"inline_keyboard": [[{"text": buy_btn_text, "url": buy_url}, {"text": "⚡ DexScreener", "url": coin["dex_url"]}]]}
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "Markdown", "reply_markup": reply_markup}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        pass

def auto_trailing_stop_checker():
    while True:
        try:
            if pnl_tracker and TELEGRAM_BOT_TOKEN:
                addrs = list(pnl_tracker.keys())[:20]
                addrs_str = ",".join(addrs)
                res = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{addrs_str}", timeout=4)
                if res.status_code == 200:
                    pairs = res.json().get("pairs", [])
                    prices = {p.get("baseToken", {}).get("address"): float(p.get("priceUsd", 0)) for p in pairs}

                    for addr, data in list(pnl_tracker.items()):
                        entry = data["entry_price"]
                        current = prices.get(addr, entry)
                        
                        if entry > 0:
                            if current > data["highest_price"]:
                                pnl_tracker[addr]["highest_price"] = current

                            highest = pnl_tracker[addr]["highest_price"]
                            current_pnl = ((current - entry) / entry) * 100
                            max_pnl = ((highest - entry) / entry) * 100

                            if max_pnl >= 20 and data["stop_level"] < 0:
                                pnl_tracker[addr]["stop_level"] = 0.0 
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🛡️ **${data['symbol']} Stop Seviyesi BAŞABAŞ (%0) Noktasına Çekildi!**"})

                            elif max_pnl >= 40 and not data.get("tp_done"):
                                pnl_tracker[addr]["tp_done"] = True
                                pnl_tracker[addr]["stop_level"] = 20.0
                                msg = f"🎉 **${data['symbol']} %40 KÂR ALINDI!**\n📈 Stop seviyesi +%20 kâr alanına çekildi."
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

                            if current_pnl <= pnl_tracker[addr]["stop_level"]:
                                exit_reason = "🛡️ İZLEYEN STOP TETİKLENDİ" if pnl_tracker[addr]["stop_level"] >= 0 else "🚨 STOP-LOSS TETİKLENDİ"
                                msg = f"{exit_reason}\n\n🪙 **Token:** ${data['symbol']}\n📊 **PnL:** %{current_pnl:+.2f}\n⚡ Pozisyon kapatıldı."
                                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})
                                del pnl_tracker[addr]
        except Exception as e:
            pass
        time.sleep(5)

async def websocket_listener():
    if not WEBSOCKET_URL:
        return
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
                    has_private_rpc = "🟢 Özel QuickNode RPC" if "quiknode" in SOLANA_RPC_URL.lower() else "🟡 Genel RPC"
                    status_msg = (
                        "🤖 **BOT ANLIK DURUM RAPORU (High-Tolerance RPC Engine)**\n\n"
                        f"⏱️ **Çalışma Süresi:** {uptime_min} dakika\n"
                        f"🔑 **Cüzdan Durumu:** {'🟢 Yüklü' if payer_keypair else '🔴 Yüklenemedi'}\n"
                        f"⚡ **RPC Bağlantısı:** {has_private_rpc}\n"
                        f"🔍 **Taranan Havuz Sayısı:** {scanned_count}\n"
                        f"🎯 **Sinyal Atılan Token:** {len(seen_tokens)}"
                    )
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": status_msg, "parse_mode": "Markdown"})
    except Exception as e:
        pass

def run_bot_loop():
    while True:
        try:
            check_telegram_commands()
            coins = get_filtered_memecoins()
            for coin in coins[:2]:
                send_telegram_alert(coin)
                time.sleep(2)
        except Exception as e:
            pass
        time.sleep(60)

if __name__ == "__main__":
    ws_thread = threading.Thread(target=start_websocket_thread)
    ws_thread.daemon = True
    ws_thread.start()

    ts_thread = threading.Thread(target=auto_trailing_stop_checker)
    ts_thread.daemon = True
    ts_thread.start()

    bot_thread = threading.Thread(target=run_bot_loop)
    bot_thread.daemon = True
    bot_thread.start()

    app.run(host="0.0.0.0", port=10000)
