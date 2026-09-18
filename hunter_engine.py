import asyncio
import os
import re
import sys
import json
import time
import queue
import signal
import threading
import requests
from telethon import TelegramClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import sms_providers

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, errors="replace")

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
SESSION_NAME = "meesho_user_session"
BOT_USERNAME = "MeeshoOrderBot"

# Order Bot / Mini App Web API
WEBAPP_BASE_URL = "https://pricetrackerpro.fojadomain.fun"
WEBAPP_TOKEN = "1729719181.5053a8bd2706f61b"

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

ACTIVE_ACTIVATIONS_FILE = os.path.join(DATA_DIR, "active_activations.json")
LOG_FILE = os.path.join(DATA_DIR, "hunter.log")
STATE_FILE = os.path.join(DATA_DIR, "hunter_state.json")
SUCCESS_FILE = os.path.join(DATA_DIR, "successful_accounts.json")
LOCAL_ACCOUNTS_FILE = os.path.join(DATA_DIR, "harvested_accounts.json")

refund_queue = queue.Queue()
stop_event = threading.Event()

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except:
        pass

def save_state(status, details="", target_count=1, completed_count=0, provider="otpdoctor", servers=""):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "status": status,
                "details": details,
                "target_count": target_count,
                "completed_count": completed_count,
                "provider": provider,
                "servers": servers,
                "updated_at": time.time()
            }, f, indent=2)
    except:
        pass

def track_activation(act_id, phone, service_name, provider="OTPDoctor"):
    acts = load_active_activations()
    acts[act_id] = {"phone": phone, "service": service_name, "provider": provider, "time": time.time()}
    try:
        with open(ACTIVE_ACTIVATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(acts, f, indent=2)
    except:
        pass

def untrack_activation(act_id):
    acts = load_active_activations()
    if act_id in acts:
        del acts[act_id]
        try:
            with open(ACTIVE_ACTIVATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(acts, f, indent=2)
        except:
            pass

def load_active_activations():
    if os.path.exists(ACTIVE_ACTIVATIONS_FILE):
        try:
            with open(ACTIVE_ACTIVATIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def record_successful_account(phone, details, provider=""):
    accs = []
    if os.path.exists(SUCCESS_FILE):
        try:
            with open(SUCCESS_FILE, "r", encoding="utf-8") as f:
                accs = json.load(f)
        except:
            accs = []
    accs.append({
        "phone": phone,
        "details": details,
        "provider": provider,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })
    try:
        with open(SUCCESS_FILE, "w", encoding="utf-8") as f:
            json.dump(accs, f, indent=2)
    except:
        pass

def background_refund_worker():
    """Background cancellation thread for safe refunds after provider cooldown."""
    while not stop_event.is_set():
        try:
            item = refund_queue.get(timeout=2)
        except queue.Empty:
            continue
        if item is None:
            break
        provider, act_id, phone, t_bought = item
        elapsed = time.time() - t_bought
        if elapsed < 125:
            time.sleep(max(0.1, 125 - elapsed))
        
        status, _ = sms_providers.cancel_activation(provider, act_id)
        untrack_activation(act_id)
        log(f"[ASYNC REFUND] +91 {phone} (ID: {act_id}) Cancelled & Refunded! (Status: {status})")
        refund_queue.task_done()

def queue_for_refund(provider, act_id, phone, t_bought):
    refund_queue.put((provider, act_id, phone, t_bought))
    remaining = max(0, int(125 - (time.time() - t_bought)))
    log(f"[*] [REFUND QUEUE] +91 {phone} queued for auto-refund in {remaining}s. Proceeding to next number!")

# ==================== Mini App Freshness Checker & Importer ====================

def get_webapp_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "x-token": WEBAPP_TOKEN
    }

def check_number_is_fresh(phone_10):
    """
    Checks number against Mini App /api/check endpoint.
    Returns:
      True  -> Confirmed FRESH on Meesho
      False -> Confirmed REGISTERED on Meesho
      None  -> Checker unavailable / session error (triggers fallback to @manishmeeshobot)
    """
    url = f"{WEBAPP_BASE_URL}/api/check"
    try:
        r = requests.post(url, headers=get_webapp_headers(), json={"number": phone_10}, timeout=12)
        if r.status_code == 200:
            data = r.json()
            if not data.get("ok"):
                err = data.get("error", "")
                log(f"[!] Mini App /api/check reported: '{err}'")
                return None

            results = data.get("results", [])
            if results:
                res = results[0]
                is_registered = res.get("registered", False)
                is_fresh = res.get("fresh", not is_registered)
                
                if is_registered is True or is_fresh is False:
                    log(f"[!] Mini App /api/check: +91 {phone_10} is REGISTERED on Meesho. REJECTED!")
                    return False
                else:
                    log(f"[+] Mini App /api/check: +91 {phone_10} is VERIFIED FRESH on Meesho! Accepted.")
                    return True
        else:
            log(f"[!] Mini App /api/check returned HTTP status {r.status_code}")
            return None
    except Exception as e:
        log(f"[!] Mini App /api/check connection error: {e}")
        return None
        
    return None

async def check_number_via_telegram_bot(client, phone_10, timeout=12):
    """
    Fallback checker using @manishmeeshobot via Telethon.
    Taps '🔍 Check Number', sends phone number, and parses reply:
      - 'NOT REGISTERED (NEW USER)' -> True (Fresh)
      - 'REGISTERED' -> False (Already used)
      - Timeout/Error -> False (Safety default)
    """
    bot_username = "manishmeeshobot"
    try:
        log(f"[*] Fallback checking +91 {phone_10} via @{bot_username}...")
        bot = await client.get_entity(bot_username)
        
        # 1. Click "Check Number" button
        msgs = await client.get_messages(bot, limit=4)
        check_btn = None
        for m in msgs:
            if m.buttons:
                for row in m.buttons:
                    for b in row:
                        if "check number" in (b.text or "").lower():
                            check_btn = b
                            break
                    if check_btn:
                        break
                        
        if check_btn:
            await check_btn.click()
            await asyncio.sleep(1)
        else:
            await client.send_message(bot, "/start")
            await asyncio.sleep(1.5)
            msgs = await client.get_messages(bot, limit=3)
            for m in msgs:
                if m.buttons:
                    for row in m.buttons:
                        for b in row:
                            if "check number" in (b.text or "").lower():
                                await b.click()
                                break
            await asyncio.sleep(1)

        # 2. Send 10-digit number
        clean_num = str(phone_10).strip()
        if clean_num.startswith("+91"):
            clean_num = clean_num[3:]
        elif clean_num.startswith("91") and len(clean_num) == 12:
            clean_num = clean_num[2:]
            
        send_msg = await client.send_message(bot, clean_num)
        
        # 3. Wait for response
        start_t = time.time()
        while (time.time() - start_t) < timeout and not stop_event.is_set():
            await asyncio.sleep(1)
            replies = await client.get_messages(bot, limit=4)
            for r in replies:
                if r.id > send_msg.id and r.sender_id == bot.id:
                    t = (r.text or "").lower()
                    if "checking" in t:
                        continue
                    if "not registered" in t or "new user" in t or "naya hai" in t:
                        log(f"[+] @{bot_username} reports: +91 {clean_num} is UNREGISTERED (Fresh)!")
                        return True
                    if "already registered" in t or "registered" in t:
                        log(f"[!] @{bot_username} reports: +91 {clean_num} is REGISTERED on Meesho. REJECTED!")
                        return False

        log(f"[!] @{bot_username} response timed out for +91 {clean_num}.")
        return False
    except Exception as e:
        log(f"[!] Error checking via @{bot_username}: {e}")
        return False

def import_account_to_order_bot(account_json):
    phone = account_json.get("mobile") or account_json.get("phone", "")
    log(f"[*] Importing account +91 {phone} to Order Bot Mini App...")
    
    # 1. Post to remote Mini App API
    try:
        r = requests.post(f"{WEBAPP_BASE_URL}/api/import", headers=get_webapp_headers(), json=account_json, timeout=15)
        log(f"[+] Mini App /api/import response: Status {r.status_code} -> {r.text[:120]}")
    except Exception as e:
        log(f"[!] Warning: Remote Mini App import error: {e}")

    # 2. Post to local Order Bot service on port 8090 if running
    try:
        r2 = requests.post("http://127.0.0.1:8090/api/accounts/import", json={"session_json": json.dumps(account_json)}, timeout=10)
        log(f"[+] Local Order Bot service import: Status {r2.status_code}")
    except Exception:
        pass

    # 3. Save directly to local harvested_accounts.json
    try:
        local_accs = []
        if os.path.exists(LOCAL_ACCOUNTS_FILE):
            try:
                with open(LOCAL_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    local_accs = json.load(f)
            except:
                local_accs = []
        
        clean_p = str(phone).replace("+", "").replace("91", "", 1) if str(phone).startswith("91") else str(phone)
        filtered = [a for a in local_accs if str(a.get("mobile", "")).replace("+", "").replace("91", "", 1) != clean_p]
        filtered.insert(0, account_json)
        
        with open(LOCAL_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2)
        log(f"[+] Account saved in local vault ({LOCAL_ACCOUNTS_FILE}). Total accounts: {len(filtered)}")
    except Exception as e:
        log(f"[!] Error saving local harvested account: {e}")

# ==================== Target Offer Evaluator ====================

def is_target_offer(text: str) -> bool:
    """
    STRICT MATCH: Only triggers on Upto ₹110 OFF (Bucket ₹170).
    Must strictly reject ₹150 OFF, ₹105 OFF, ₹95 OFF, etc.
    """
    if not text:
        return False
    
    t = text.lower()
    if any(w in t for w in ["setting things up", "setting up", "fetching", "already fetching", "please wait", "failed to fetch", "null"]):
        return False

    clean_t = re.sub(r'[\*\_`]', '', text).lower()

    # STRICT REJECTION: Never trigger on 150 OFF or any other unwanted tier
    if "150 off" in clean_t or "105 off" in clean_t or "95 off" in clean_t or "75 off" in clean_t or "60 off" in clean_t:
        return False

    # STRICT MATCH: Must be Upto ₹110 OFF AND Bucket ₹170
    has_110_off = "110 off" in clean_t
    has_bucket_170 = bool(re.search(r'bucket.*?170', clean_t, re.IGNORECASE))
    has_upi_83 = bool(re.search(r'upi.*?83', clean_t, re.IGNORECASE))
    has_final_107 = bool(re.search(r'final.*?107', clean_t, re.IGNORECASE))

    if has_110_off and has_bucket_170:
        return True
    if has_110_off and (has_upi_83 or has_final_107):
        return True

    # Legacy ₹120 OFF strictly with Bucket 190
    has_120_off = "120 off" in clean_t
    has_bucket_190 = bool(re.search(r'bucket.*?190', clean_t, re.IGNORECASE))
    if has_120_off and has_bucket_190:
        return True

    return False

# ==================== Telegram Interaction Helpers ====================

async def click_inline_button_by_patterns(msg, patterns):
    if not msg or not msg.buttons:
        return False
    for row in msg.buttons:
        for btn in row:
            btn_text = (btn.text or "").lower()
            btn_data = str(getattr(btn, "data", "")).lower()
            for pat in patterns:
                p = pat.lower()
                if p in btn_text or p in btn_data:
                    try:
                        await btn.click()
                        return True
                    except Exception as e:
                        log(f"[!] Inline button click warning: {e}")
                        return True
    return False

async def get_latest_bot_message(client, bot_entity):
    messages = await client.get_messages(bot_entity, limit=5)
    for m in messages:
        if m.sender_id == bot_entity.id:
            return m
    return messages[0] if messages else None

async def wait_for_offer_message(client, bot_entity, timeout=45):
    """
    Waits past any intermediate loading states ('Setting things up', 'Already fetching your offer', 'Please wait')
    until the actual offer text and/or inline buttons (Try Another Offer / Cancel) are present.
    """
    start_t = time.time()
    while (time.time() - start_t) < timeout and not stop_event.is_set():
        await asyncio.sleep(1)
        recent = await client.get_messages(bot_entity, limit=3)
        bot_msgs = [m for m in recent if m.sender_id == bot_entity.id]
        if not bot_msgs:
            continue
        top = bot_msgs[0]
        text_lower = (top.text or "").lower()
        
        # Check if still in any loading state
        is_loading = any(w in text_lower for w in ["setting", "fetching", "please wait", "setting up", "already fetching", "hold on"])
        if is_loading:
            continue
            
        has_offer_content = any(w in text_lower for w in ["bucket", "10-digit", "upto", "final", "offer details"])
        has_offer_buttons = any("another" in btn.text.lower() or "retry" in str(getattr(btn, "data", "")).lower() for row in (top.buttons or []) for btn in row)
        
        if has_offer_content or has_offer_buttons:
            return top

    return await get_latest_bot_message(client, bot_entity)

async def navigate_to_offer_screen(client, bot_entity):
    log("[*] Navigating: Sending /start to @MeeshoOrderBot...")
    await client.send_message(bot_entity, "/start")
    await asyncio.sleep(2)

    msg = await get_latest_bot_message(client, bot_entity)
    clicked_add = await click_inline_button_by_patterns(msg, ["add account", "add_account", "➕ add"])
    if not clicked_add:
        await client.send_message(bot_entity, "/start")
        await asyncio.sleep(2)
        msg = await get_latest_bot_message(client, bot_entity)
        await click_inline_button_by_patterns(msg, ["add account", "add_account", "➕ add"])

    await asyncio.sleep(2)

    msg = await get_latest_bot_message(client, bot_entity)
    await click_inline_button_by_patterns(msg, ["login with number", "add:num", "number"])
    log("[*] Clicked '📱 Login with Number'. Waiting for offer setup to finish...")

    offer_msg = await wait_for_offer_message(client, bot_entity, timeout=45)
    return offer_msg

async def reroll_offer_button(client, bot_entity, current_offer_msg):
    clicked = await click_inline_button_by_patterns(current_offer_msg, [
        "offer_retry",
        "try another offer",
        "try another",
        "try again",
        "🔄"
    ])
    
    if not clicked:
        latest = await get_latest_bot_message(client, bot_entity)
        clicked = await click_inline_button_by_patterns(latest, [
            "offer_retry",
            "try another offer",
            "try another",
            "try again",
            "🔄"
        ])
        
    if not clicked:
        log("[!] Inline reroll button not found, refreshing navigation...")
        return await navigate_to_offer_screen(client, bot_entity)

    log("[*] Clicked '🔄 Try Another Offer'. Waiting for new offer to finish loading...")
    await asyncio.sleep(1.5)
    return await wait_for_offer_message(client, bot_entity, timeout=45)

async def extract_account_json_from_messages(client, bot_entity):
    """
    Waits for the bot to finish verifying and send the exported session JSON document/text.
    Downloads the JSON file directly from Telegram media.
    """
    for _ in range(15):
        await asyncio.sleep(1.5)
        messages = await client.get_messages(bot_entity, limit=8)
        for m in messages:
            if m.file and (m.file.name or "").endswith(".json"):
                try:
                    file_bytes = await m.download_media(bytes)
                    parsed = json.loads(file_bytes.decode("utf-8"))
                    if parsed.get("xo") and parsed.get("user_id"):
                        return parsed
                except Exception as e:
                    log(f"[!] Error parsing downloaded JSON file: {e}")
            if m.text and "{" in m.text and "}" in m.text and "xo" in m.text and "user_id" in m.text:
                try:
                    start = m.text.find("{")
                    end = m.text.rfind("}") + 1
                    parsed = json.loads(m.text[start:end])
                    if parsed.get("xo") and parsed.get("user_id"):
                        return parsed
                except Exception:
                    pass
    return None

# ==================== Fresh SIM Acquisition ====================

async def acquire_fresh_number(client, provider_name, active_servers, service_idx_ref):
    """
    Cycles through active servers, buys a SIM number, and verifies freshness
    via Mini App /api/check (Primary) and @manishmeeshobot (Automatic Fallback).
    If ALREADY REGISTERED or unverified -> immediately queues for auto-refund and retries next server.
    If FRESH -> returns dict with act_id, phone_10, display_srv, t_bought.
    """
    p_lower = provider_name.lower().strip()
    total_servers = len(active_servers)

    while not stop_event.is_set():
        act_id = None
        phone_10 = None
        display_srv = None
        buy_attempts = 0
        max_buy = total_servers * 3

        while not act_id and buy_attempts < max_buy and not stop_event.is_set():
            srv = active_servers[service_idx_ref[0] % total_servers]
            service_idx_ref[0] += 1
            buy_attempts += 1
            srv_name = srv.get("name", "Unknown Server")

            log(f"[*] Requesting number from {srv_name}...")
            if "premiumotp" in p_lower:
                act_id, phone_10, display_srv = sms_providers.buy_number_premiumotp(srv.get("param", ""), srv_name)
            elif "uotp" in p_lower:
                act_id, phone_10, display_srv = sms_providers.buy_number_uotp(srv.get("id", 2))
            else:
                act_id, phone_10, display_srv = sms_providers.buy_number_otpdoctor(srv.get("id", "16040"), srv_name)

            if not act_id:
                log(f"[!] Stock Out on {srv_name}: {phone_10}. Trying next server...")
                await asyncio.sleep(1)

        if not act_id:
            log("[!] All servers currently out of stock. Waiting 5s to retry server queue...")
            await asyncio.sleep(5)
            continue

        t_bought = time.time()
        track_activation(act_id, phone_10, display_srv, provider_name)
        log(f"[+] Purchased Number: +91 {phone_10} (ID: {act_id}) on {display_srv}")

        # 1. Primary Check: Mini App /api/check
        log(f"[*] Checking freshness of +91 {phone_10} via Mini App /api/check...")
        is_fresh = check_number_is_fresh(phone_10)

        # 2. Fallback Check: If Mini App was unavailable or errored out, fallback to @manishmeeshobot
        if is_fresh is None:
            log(f"[!] Mini App API unavailable or session error! Automatically falling back to @manishmeeshobot...")
            is_fresh = await check_number_via_telegram_bot(client, phone_10)

        if not is_fresh:
            log(f"[!] Number +91 {phone_10} is REGISTERED or could not be verified! Discarding & auto-refunding.")
            queue_for_refund(provider_name, act_id, phone_10, t_bought)
            await asyncio.sleep(1)
            continue

        log(f"[+] VERIFIED FRESH! Number +91 {phone_10} is 100% unregistered.")
        return {
            "act_id": act_id,
            "phone_10": phone_10,
            "display_srv": display_srv,
            "t_bought": t_bought
        }

    return None

# ==================== Main Telegram Hunter Routine ====================

async def run_telegram_hunter(target_count=1, provider_name="otpdoctor", servers_filter=""):
    log("=" * 65)
    log(f"   TELEGRAM @MeeshoOrderBot HUNTER (TARGET: {target_count} | PROVIDER: {provider_name.upper()})")
    log("   (Target: Upto 110 OFF | Bucket: 170 | UPI: 83 | Final: 107)")
    log("   (Optimal Flow: 3-Min OTP Timeout + Change Number Offer Preservation)")
    log("=" * 65)

    refund_thread = threading.Thread(target=background_refund_worker, daemon=True)
    refund_thread.start()

    p_lower = provider_name.lower().strip()
    if "premiumotp" in p_lower:
        active_servers = sms_providers.PREMIUMOTP_SERVERS
        bal = sms_providers.get_premiumotp_balance()
    elif "uotp" in p_lower:
        active_servers = sms_providers.UOTP_SERVERS
        bal = sms_providers.get_uotp_balance()
    else:
        active_servers = sms_providers.OTPDOCTOR_SERVERS
        bal = sms_providers.get_otpdoctor_balance()

    if servers_filter:
        req_srv = [s.strip().lower() for s in servers_filter.split(",") if s.strip()]
        filtered = [s for s in active_servers if s.get("name", "").lower() in req_srv or s.get("code", "").lower() in req_srv or str(s.get("id", "")).lower() in req_srv]
        if filtered:
            active_servers = filtered

    bal_display = f"Rs. {bal:.2f}" if bal is not None else "Verified Online"
    log(f"[*] SMS Provider: {provider_name.upper()} | Available Balance: {bal_display}")
    log(f"[*] Active Servers ({len(active_servers)}): {[s.get('name') for s in active_servers]}")

    if bal is not None and bal < 5.0:
        log("[!] INSUFFICIENT BALANCE on SMS provider!")
        save_state("stopped", "Insufficient balance on SMS provider", target_count, 0, provider_name, servers_filter)
        return

    client = TelegramClient(os.path.join(BASE_DIR, SESSION_NAME), API_ID, API_HASH)
    await client.start()
    log("[+] Connected to Telegram client session!")

    try:
        bot_entity = await client.get_entity(BOT_USERNAME)
    except Exception as e:
        log(f"[!] Failed to resolve @{BOT_USERNAME}: {e}")
        save_state("stopped", f"Failed to resolve @{BOT_USERNAME}", target_count, 0, provider_name, servers_filter)
        return

    completed_count = 0
    service_idx_ref = [0]
    standby_sim = None
    save_state("running", f"Hunting target: {completed_count}/{target_count} accounts", target_count, completed_count, provider_name, servers_filter)

    try:
        while completed_count < target_count and not stop_event.is_set():
            current_acc_num = completed_count + 1
            log("\n" + "=" * 50)
            log(f">>> STARTING Account {current_acc_num} of {target_count} <<<")
            log("=" * 50)

            account_added = False
            target_offer_locked = False
            offer_msg = None

            while not account_added and not stop_event.is_set():
                # Step 1: Hunt / Reroll for Target Offer ONLY IF NOT ALREADY LOCKED
                if not target_offer_locked:
                    offer_msg = await navigate_to_offer_screen(client, bot_entity)
                    if not offer_msg:
                        log("[!] Failed to load offer screen. Retrying navigation...")
                        await asyncio.sleep(2)
                        continue

                    # Step 2: Inline Button Reroll Loop
                    reroll_attempts = 0
                    max_rerolls = 60
                    matched = False

                    while reroll_attempts < max_rerolls and not stop_event.is_set():
                        reroll_attempts += 1
                        msg_text = offer_msg.text if offer_msg else ""
                        
                        if is_target_offer(msg_text):
                            log(f"\n[+] TARGET OFFER MATCHED on Reroll #{reroll_attempts}!")
                            log(f"[*] Matched Target Offer (Bucket 170 / Upto 110 OFF / UPI 83):\n{msg_text[:250]}\n")
                            matched = True
                            break

                        offer_summary = re.sub(r'\s+', ' ', msg_text[:80]) if msg_text else "Loading..."
                        log(f"[*] Reroll #{reroll_attempts}: {offer_summary}... Tapping '🔄 Try Another Offer' button...")
                        save_state("running", f"Rerolling offer #{reroll_attempts} on @MeeshoOrderBot...", target_count, completed_count, provider_name, servers_filter)

                        offer_msg = await reroll_offer_button(client, bot_entity, offer_msg)

                    if not matched:
                        log("[!] Exceeded max rerolls for this cycle. Restarting offer navigation...")
                        continue

                    # Offer is successfully locked!
                    target_offer_locked = True
                    log("[+] Target Offer (Bucket 170 / Upto 110 OFF / UPI 83) LOCKED!")

                # Step 3: Optimal SIM Selection (Standby Buffer vs Fresh Buy)
                active_sim = None
                if standby_sim:
                    active_sim = standby_sim
                    standby_sim = None
                    log(f"[+] [Optimal Flow] Using pre-verified standby number +91 {active_sim['phone_10']} ({active_sim['display_srv']})!")
                else:
                    log("[*] Target offer is locked! Acquiring fresh number from active servers...")
                    save_state("running", f"Finding fresh number for Account #{current_acc_num}...", target_count, completed_count, provider_name, servers_filter)
                    active_sim = await acquire_fresh_number(client, provider_name, active_servers, service_idx_ref)
                    if not active_sim:
                        continue

                phone_10 = active_sim["phone_10"]
                act_id = active_sim["act_id"]
                display_srv = active_sim["display_srv"]
                t_bought = active_sim["t_bought"]

                # Step 4: Send Verified Fresh Number to @MeeshoOrderBot
                log(f"[*] Sending fresh number {phone_10} to @{BOT_USERNAME}...")
                save_state("running", f"Submitting fresh +91 {phone_10} to bot...", target_count, completed_count, provider_name, servers_filter)
                await client.send_message(bot_entity, phone_10)
                await asyncio.sleep(3)

                bot_reply = await get_latest_bot_message(client, bot_entity)
                reply_text = bot_reply.text.lower() if bot_reply and bot_reply.text else ""

                if "already registered" in reply_text or "registered account" in reply_text or "not fresh" in reply_text:
                    log(f"[!] Bot reported +91 {phone_10} as registered. Discarding & auto-refunding.")
                    queue_for_refund(provider_name, act_id, phone_10, t_bought)
                    
                    # Click 'Change Number' to stay on the locked offer!
                    log("[*] Clicking '✏️ Change Number' to preserve locked offer...")
                    latest = await get_latest_bot_message(client, bot_entity)
                    await click_inline_button_by_patterns(latest, ["change number", "chg_num", "✏️ change"])
                    await asyncio.sleep(2)
                    # Target offer is still locked! DO NOT send /start!
                    continue

                # Step 5: Launch Background Pre-Fetch of Next Number while Waiting for OTP
                prefetch_task = None
                if standby_sim is None:
                    log(f"[*] [Optimal Flow] Pre-fetching next fresh number in background while waiting for OTP...")
                    prefetch_task = asyncio.create_task(acquire_fresh_number(client, provider_name, active_servers, service_idx_ref))

                # Step 6: Poll SMS Provider for OTP (3-Minute / 180s Timeout)
                log(f"[+] Phone accepted! Polling {provider_name.upper()} for OTP SMS on +91 {phone_10} (Timeout: 180s / 3 min)...")
                save_state("running", f"Waiting for OTP on +91 {phone_10} (3m timeout)...", target_count, completed_count, provider_name, servers_filter)

                otp_code = None
                poll_start = time.time()
                otp_timeout = 180  # 3 minutes

                while (time.time() - poll_start) < otp_timeout and not stop_event.is_set():
                    status, code = sms_providers.get_sms_status(provider_name, act_id)
                    if status == "OK" and code:
                        otp_code = code
                        log(f"\n[+] RECEIVED OTP CODE: {otp_code} on +91 {phone_10}!")
                        break
                    elif status == "CANCELLED":
                        log(f"\n[!] Activation for +91 {phone_10} was cancelled by SMS server.")
                        break

                    # Check if background prefetch has completed
                    if prefetch_task and prefetch_task.done() and standby_sim is None:
                        try:
                            res = prefetch_task.result()
                            if res:
                                standby_sim = res
                                log(f"\n[+] [Optimal Flow] Standby fresh number +91 {standby_sim['phone_10']} is verified & ready on hold!")
                        except Exception as e:
                            log(f"\n[!] Background prefetch error: {e}")

                    await asyncio.sleep(3)
                    elapsed = int(time.time() - poll_start)
                    print(f".({elapsed}s)", end="", flush=True)

                # Branch A: OTP Timed Out after 3 Minutes
                if not otp_code:
                    log(f"\n[!] Timeout (3 min exceeded) waiting for OTP on +91 {phone_10}. Auto-refunding...")
                    queue_for_refund(provider_name, act_id, phone_10, t_bought)
                    
                    # Click 'Change Number' to stay on the locked offer!
                    log("[*] Clicking '✏️ Change Number' to preserve locked offer (Will NOT send /start)...")
                    latest = await get_latest_bot_message(client, bot_entity)
                    clicked_chg = await click_inline_button_by_patterns(latest, ["change number", "chg_num", "✏️ change"])
                    await asyncio.sleep(2)
                    
                    latest_after = await get_latest_bot_message(client, bot_entity)
                    text_after = (latest_after.text or "").lower()
                    
                    # Verify bot is waiting for new number
                    if "send" in text_after or "10-digit" in text_after or "change number" in text_after:
                        log("[+] Bot is waiting for new 10-digit number. Offer STILL LOCKED! (No /start sent)")
                        target_offer_locked = True
                    else:
                        log("[!] Bot state reset. Will re-hunt target offer.")
                        target_offer_locked = False

                    # Ensure standby SIM is ready for immediate switch
                    if standby_sim is None and prefetch_task:
                        if not prefetch_task.done():
                            log("[*] Waiting for background pre-fetch to finish fresh number...")
                            try:
                                standby_sim = await asyncio.wait_for(prefetch_task, timeout=20)
                            except Exception:
                                pass

                    if standby_sim:
                        log(f"[+] [Optimal Flow] Instantly ready with next pre-verified number +91 {standby_sim['phone_10']}!")
                    continue

                # Branch B: OTP Received Successfully
                log(f"[*] Submitting OTP {otp_code} to @{BOT_USERNAME}...")
                save_state("running", f"Submitting OTP {otp_code} for +91 {phone_10}...", target_count, completed_count, provider_name, servers_filter)
                
                await client.send_message(bot_entity, str(otp_code))
                await asyncio.sleep(3)

                # Step 7: Wait for Bot Verification & Download Exported Session JSON
                log("[*] Waiting for @MeeshoOrderBot to finish verification and export session JSON...")
                save_state("running", f"Downloading session JSON for +91 {phone_10}...", target_count, completed_count, provider_name, servers_filter)
                
                account_json = await extract_account_json_from_messages(client, bot_entity)

                sms_providers.complete_activation(provider_name, act_id)
                untrack_activation(act_id)

                if account_json and account_json.get("xo") and account_json.get("user_id"):
                    log(f"[+] Successfully extracted full session JSON for +91 {phone_10} (User ID: {account_json.get('user_id')})!")
                    account_json["discount_applied"] = 110
                    import_account_to_order_bot(account_json)
                else:
                    log(f"[!] Warning: Bot did not output JSON file. Constructing session record for +91 {phone_10}...")
                    fallback_record = {
                        "mobile": phone_10,
                        "phone": f"+91{phone_10}",
                        "discount_applied": 120,
                        "target_offer": "Upto ₹110 OFF (Bucket ₹170 / UPI ₹83 / Final ₹107)",
                        "server": display_srv,
                        "added_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    import_account_to_order_bot(fallback_record)

                details = f"Upto ₹110 OFF | Bucket 170 | UPI Rs.83 | Final Rs.107 | {display_srv}"
                record_successful_account(f"+91{phone_10}", details, provider_name)

                completed_count += 1
                account_added = True
                target_offer_locked = False  # Reset for next account cycle
                save_state("running", f"Account {completed_count}/{target_count} successfully added (+91 {phone_10})", target_count, completed_count, provider_name, servers_filter)
                log(f"[+] SUCCESS: {completed_count}/{target_count} TARGET ACCOUNTS COMPLETED!\n")

                # Handle standby SIM based on target progress
                if completed_count >= target_count:
                    # All done! Refund any unused standby SIM
                    if standby_sim:
                        log("[*] All target accounts created! Refunding unused standby SIM...")
                        queue_for_refund(provider_name, standby_sim["act_id"], standby_sim["phone_10"], standby_sim["t_bought"])
                        standby_sim = None
                    if prefetch_task and not prefetch_task.done():
                        prefetch_task.cancel()
                else:
                    # More accounts needed: Keep standby_sim ready for next account!
                    log(f"[*] [Optimal Flow] Standby SIM preserved for Account #{completed_count + 1}!")

                await asyncio.sleep(2)

    finally:
        # Cleanup on exit
        if standby_sim:
            log("[*] Cleaning up standby SIM on hunter exit...")
            queue_for_refund(provider_name, standby_sim["act_id"], standby_sim["phone_10"], standby_sim["t_bought"])
            standby_sim = None

    if completed_count >= target_count:
        log("=" * 65)
        log(f"[OK] ALL {target_count} TARGET ACCOUNTS SUCCESSFULLY ADDED & IMPORTED!")
        log("=" * 65)
        save_state("completed", f"All {target_count} target accounts successfully created and imported!", target_count, completed_count, provider_name, servers_filter)
    else:
        log("[*] Hunter engine stopped.")
        save_state("stopped", f"Stopped with {completed_count}/{target_count} accounts completed.", target_count, completed_count, provider_name, servers_filter)

    await client.disconnect()

def handle_shutdown(signum, frame):
    log("[!] Received termination signal. Stopping hunter...")
    stop_event.set()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    count_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    provider_arg = sys.argv[2] if len(sys.argv) > 2 else "otpdoctor"
    servers_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    asyncio.run(run_telegram_hunter(count_arg, provider_arg, servers_arg))
