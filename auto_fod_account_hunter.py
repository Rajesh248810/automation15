from dotenv import load_dotenv
load_dotenv()
import requests
import json
import time
import re
import sys
import os
import threading
import queue

# Unbuffered stdout for real-time live console logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, errors="replace")

# Configuration
OTP_API_KEY = os.getenv("OTPDOCTOR_API_KEY", "")
OTP_BASE_URL = "https://www.otpdoctor.in/stubs/handler_api.php"

BOT_BASE_URL = "os.getenv("WEBAPP_BASE_URL", "https://pricetrackerpro.fojadomain.fun")"
BOT_TOKEN = os.getenv("WEBAPP_TOKEN", "")

TARGET_ACCOUNTS_COUNT = 1
TIER = 180  # Max Tier for Rs. 213 FOD / Rs. 9-15 UPI

# Services sorted by price ascending (cheapest first)
SERVICES_QUEUE = [
    {"id": "13915", "name": "Meesho IN-C", "price": 8.0},
    {"id": "12843", "name": "Meesho IN-A", "price": 8.5},
    {"id": "19826", "name": "Meesho IN-9", "price": 9.0},
    {"id": "5655", "name": "Meesho MultiSms IN-6", "price": 9.5},
    {"id": "10619", "name": "Meesho MultiSms IN-3", "price": 9.5},
    {"id": "16487", "name": "Meesho 2 MultiSms IN-1", "price": 9.5},
    {"id": "20317", "name": "Meesho IN-5", "price": 10.0},
    {"id": "7308", "name": "Meesho IN-13", "price": 10.0},
    {"id": "9318", "name": "Meesho MultiSms IN-1", "price": 11.5},
    {"id": "11642", "name": "Meesho 2 MultiSms IN-3", "price": 11.5},
    {"id": "6038", "name": "Meesho IN-4", "price": 12.0},
    {"id": "16040", "name": "Meesho MultiSms IN-2", "price": 12.0},
    {"id": "5841", "name": "Meesho IN-8", "price": 12.0},
    {"id": "20325", "name": "Meesho IN-14", "price": 13.0}
]

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "harvested_accounts.json")

# Background cancellation queue so main thread never waits
cancel_queue = queue.Queue()

def background_cancellation_worker():
    """Monitors and cancels rejected activations in background after cooldown to ensure 100% refunds."""
    while True:
        item = cancel_queue.get()
        if item is None:
            break
        act_id, phone_10, t_bought = item
        elapsed = time.time() - t_bought
        if elapsed < 125:
            time.sleep(125 - elapsed)
        res = otp_set_status(act_id, 8)
        print(f"\n[ASYNC REFUND] +91 {phone_10} (ID: {act_id}) Cancelled & Refunded! (Status: {res})\n", flush=True)
        cancel_queue.task_done()

def queue_for_background_refund(act_id, phone_10, t_bought):
    cancel_queue.put((act_id, phone_10, t_bought))
    remaining = max(0, int(125 - (time.time() - t_bought)))
    print(f"[*] [BACKGROUND QUEUE] +91 {phone_10} queued for auto-refund in {remaining}s. Moving to NEXT NUMBER immediately!", flush=True)

def get_bot_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "x-token": BOT_TOKEN
    }

# ==================== OTPDoctor API Helpers ====================

def otp_get_balance():
    url = f"{OTP_BASE_URL}?action=getBalance&api_key={OTP_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        if "ACCESS_BALANCE:" in r.text:
            return float(r.text.split("ACCESS_BALANCE:")[1].strip())
    except Exception as e:
        print(f"[!] Error fetching balance: {e}")
    return 0.0

def otp_buy_number(service_id):
    url = f"{OTP_BASE_URL}?action=getNumber&api_key={OTP_API_KEY}&service={service_id}"
    try:
        r = requests.get(url, timeout=15)
        text = r.text.strip()
        if "ACCESS_NUMBER:" in text:
            parts = text.split(":")
            activation_id = parts[1]
            phone = parts[2]
            phone_10 = phone[-10:] if len(phone) >= 10 else phone
            return activation_id, phone_10
        else:
            return None, text
    except Exception as e:
        return None, str(e)

def otp_get_status(activation_id):
    url = f"{OTP_BASE_URL}?action=getStatus&api_key={OTP_API_KEY}&id={activation_id}"
    try:
        r = requests.get(url, timeout=10)
        text = r.text.strip()
        if "STATUS_OK:" in text:
            code_match = re.findall(r'\b\d{4,6}\b', text.split("STATUS_OK:")[1])
            return "OK", code_match[0] if code_match else text.split("STATUS_OK:")[1].strip()
        elif "STATUS_WAIT_CODE" in text:
            return "WAIT", None
        elif "STATUS_CANCEL" in text:
            return "CANCELLED", None
        else:
            return text, None
    except Exception as e:
        return "ERROR", str(e)

def otp_set_status(activation_id, status_code):
    """status_code: 8 = Cancel, 6 = Finish/Complete, 3 = Request another SMS"""
    url = f"{OTP_BASE_URL}?action=setStatus&api_key={OTP_API_KEY}&id={activation_id}&status={status_code}"
    try:
        r = requests.get(url, timeout=10)
        return r.text.strip()
    except Exception as e:
        return f"ERROR: {e}"

# ==================== Bot API Helpers ====================

def bot_start_hunt(phone_10):
    url = f"{BOT_BASE_URL}/api/login/start"
    payload = {"phone": phone_10, "referral": "", "tier": TIER}
    try:
        r = requests.post(url, headers=get_bot_headers(), json=payload, timeout=140)
        if r.status_code == 200:
            return r.json()
        return {"ok": False, "error": f"HTTP_{r.status_code}", "raw": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def bot_send_otp():
    url = f"{BOT_BASE_URL}/api/login/send_otp"
    try:
        r = requests.post(url, headers=get_bot_headers(), json={}, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def bot_verify_otp(otp_code):
    url = f"{BOT_BASE_URL}/api/login/verify"
    try:
        r = requests.post(url, headers=get_bot_headers(), json={"otp": str(otp_code)}, timeout=25)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ==================== Main Engine Loop ====================

def save_account_to_file(acc_data):
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
        except Exception:
            accounts = []
    accounts.append(acc_data)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2)
    print(f"[+] Account saved to {ACCOUNTS_FILE}!")

def main():
    print("=" * 65)
    print("   MEESHO Rs. 213 FOD AUTO-HUNT (ASYNC FAST-PIPELINE ENGINE)")
    print("=" * 65)
    
    # Start background refund worker thread
    refund_thread = threading.Thread(target=background_cancellation_worker, daemon=True)
    refund_thread.start()
    
    bal = otp_get_balance()
    print(f"[*] Current OTPDoctor Balance: Rs. {bal:.2f}")
    if bal < 8.0:
        print("[!] Insufficient balance on OTPDoctor!")
        return

    accounts_created = 0
    service_idx = 0
    total_services = len(SERVICES_QUEUE)

    while accounts_created < TARGET_ACCOUNTS_COUNT:
        service = SERVICES_QUEUE[service_idx % total_services]
        print("\n" + "-" * 65)
        print(f"[*] Account #{accounts_created + 1}/{TARGET_ACCOUNTS_COUNT} | Trying Service: {service['name']} (Rs. {service['price']})")
        print("-" * 65)
        
        act_id, phone_10 = otp_buy_number(service["id"])
        
        if not act_id:
            print(f"[!] Stock Out on {service['name']}: {phone_10}. Trying next service...")
            service_idx += 1
            time.sleep(1)
            continue
            
        t_bought = time.time()
        print(f"[+] Purchased Number: +91 {phone_10} (ID: {act_id})")
        
        # Step 1: Check registration and Hunt Offer on Bot
        print(f"[*] Hunting Tier {TIER} on +91 {phone_10}...")
        hunt_res = bot_start_hunt(phone_10)
        
        is_registered = hunt_res.get("registered", False)
        fod_value = hunt_res.get("fod_value", 0)
        upi_amount = hunt_res.get("upi_amount", 999)
        is_target = hunt_res.get("is_target", False)
        
        print(f"[*] Result: Registered={is_registered} | FOD=Rs.{fod_value} | UPI=Rs.{upi_amount} | TargetMet={is_target}")
        
        # Case A: Number is already registered on Meesho
        if is_registered:
            print(f"[!] Number +91 {phone_10} is ALREADY REGISTERED.")
            queue_for_background_refund(act_id, phone_10, t_bought)
            service_idx += 1
            continue
            
        # Case B: Fresh Number & Hits the Rs. 213 Target
        target_qualified = is_target or (fod_value >= 213) or (upi_amount is not None and upi_amount <= 15)
        
        # If fresh but target missed, retry hunt once quickly
        if not target_qualified and (time.time() - t_bought) < 60:
            print("[*] Fresh number missed target. Re-hunting...")
            time.sleep(1)
            hunt_res = bot_start_hunt(phone_10)
            fod_value = hunt_res.get("fod_value", 0)
            upi_amount = hunt_res.get("upi_amount", 999)
            is_target = hunt_res.get("is_target", False)
            target_qualified = is_target or (fod_value >= 213) or (upi_amount is not None and upi_amount <= 15)
            print(f"[*] 2nd Hunt Result: FOD=Rs.{fod_value} | UPI=Rs.{upi_amount} | TargetMet={is_target}")
            
        if not target_qualified:
            print(f"[!] Number +91 {phone_10} missed target discount.")
            queue_for_background_refund(act_id, phone_10, t_bought)
            service_idx += 1
            continue
            
        # Case C: TARGET HIT! Send OTP and Verify
        print(f"\n[+] JACKPOT! Fresh number +91 {phone_10} qualified for Rs. 213 Discount (UPI Rs. {upi_amount})!")
        print("[*] Sending OTP via Bot...")
        otp_send_res = bot_send_otp()
        
        if not otp_send_res.get("ok"):
            print(f"[!] Failed to send OTP: {otp_send_res.get('error')}")
            queue_for_background_refund(act_id, phone_10, t_bought)
            service_idx += 1
            continue
            
        print(f"[*] OTP Sent successfully! Polling OTPDoctor (Max 120s)...")
        
        # Poll for OTP
        otp_received = None
        poll_start = time.time()
        while time.time() - poll_start < 120:
            status, code = otp_get_status(act_id)
            if status == "OK" and code:
                otp_received = code
                print(f"\n[+] RECEIVED OTP: {otp_received}")
                break
            elif status == "CANCELLED":
                print("\n[!] Activation was cancelled by server.")
                break
            time.sleep(3)
            print(".", end="", flush=True)
            
        if not otp_received:
            print(f"\n[!] Timed out waiting for OTP on +91 {phone_10}.")
            queue_for_background_refund(act_id, phone_10, t_bought)
            service_idx += 1
            continue
            
        # Verify OTP on Bot
        print(f"[*] Verifying OTP {otp_received} on Bot...")
        verify_res = bot_verify_otp(otp_received)
        
        if verify_res.get("ok"):
            print(f"[OK] SUCCESS! Account +91 {phone_10} added to your Telegram bot!")
            otp_set_status(act_id, 6)  # Mark finished on OTPDoctor
            
            acc_record = {
                "phone": f"+91{phone_10}",
                "fod_value": fod_value,
                "upi_amount": upi_amount,
                "added_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_account_to_file(acc_record)
            accounts_created += 1
            print(f"[*] Target Progress: {accounts_created}/{TARGET_ACCOUNTS_COUNT}")
        else:
            print(f"[!] OTP Verification failed: {verify_res}")
            queue_for_background_refund(act_id, phone_10, t_bought)
            
        time.sleep(2)

    print("\n" + "=" * 65)
    print(f"[OK] ALL {TARGET_ACCOUNTS_COUNT} TARGET ACCOUNTS ADDED TO TELEGRAM BOT!")
    print(f"[*] Final OTPDoctor Balance: Rs. {otp_get_balance():.2f}")
    print("=" * 65)

if __name__ == "__main__":
    main()
