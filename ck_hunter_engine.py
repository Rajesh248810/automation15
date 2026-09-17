from dotenv import load_dotenv
load_dotenv()
import asyncio
import time
import requests
import sys
import os
from telethon import TelegramClient
from telethon.tl.custom import Button

API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_FILE = "ck_session_alt"
BOT_USERNAME = "ckmeesho_bot"

PREMIUM_OTP_KEY = os.getenv("PREMIUMOTP_API_KEY", "")
SERVICE_CODE = "hp"

ALL_SERVERS = {
    'premium_in14': 'India server 14',
    'premium_in11': 'India Server 11',
    'premium_in3': 'India Server 3',
    'premium_in25': 'India server 25',
    'premium_in19': 'India Server 19'
}

# The servers will be passed via command line, comma separated.
selected_server_keys = sys.argv[1].split(',') if len(sys.argv) > 1 else list(ALL_SERVERS.keys())
SERVERS = [ALL_SERVERS[k] for k in selected_server_keys if k in ALL_SERVERS]
if not SERVERS:
    SERVERS = list(ALL_SERVERS.values())

async def premium_get_number(server):
    url = f"https://premiumotp.pro/api/v1/stark?api_key={PREMIUM_OTP_KEY}&action=getNumber&service={SERVICE_CODE}&server={server}"
    try:
        res = requests.get(url, timeout=10).text
        if "ACCESS_NUMBER" in res:
            parts = res.split(":")
            return {"id": parts[1], "number": parts[2]}
        print(f"[{server}] Get Number Failed: {res}")
    except Exception as e:
        print(f"[{server}] API Error: {e}")
    return None

async def premium_get_status(order_id):
    url = f"https://premiumotp.pro/api/v1/stark?api_key={PREMIUM_OTP_KEY}&action=getStatus&id={order_id}"
    try:
        res = requests.get(url, timeout=10).text
        if "STATUS_OK" in res:
            return res.split(":")[1]
        elif "STATUS_WAIT_CODE" in res:
            return "WAIT"
    except:
        pass
    return None

async def premium_cancel(order_id):
    url = f"https://premiumotp.pro/api/v1/stark?api_key={PREMIUM_OTP_KEY}&action=setStatus&status=8&id={order_id}"
    try:
        requests.get(url, timeout=10)
    except:
        pass

async def click_button_with_text(conv, text):
    msg = await conv.get_response()
    if msg.buttons:
        for row in msg.buttons:
            for btn in row:
                if text.lower() in btn.text.lower():
                    await btn.click()
                    return True
    await conv.send_message(text)
    return False

async def hunt_loop():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    
    print(f"[*] Starting CK Premium Hunter on servers: {SERVERS}")
    server_idx = 0

    while True:
        # Check stop flag
        if os.path.exists("ck_stop.flag"):
            print("[*] Stop flag found. Exiting...")
            break
            
        server = SERVERS[server_idx % len(SERVERS)]
        server_idx += 1
        
        print(f"[*] Trying to get number from {server}...")
        num_data = await premium_get_number(server)
        
        if not num_data:
            await asyncio.sleep(5)
            continue
            
        order_id = num_data['id']
        phone = num_data['number']
        clean_phone = phone.replace("+", "").replace(" ", "")
        print(f"[+] Got Number: {clean_phone} (Order ID: {order_id})")
        
        try:
            async with client.conversation(BOT_USERNAME, timeout=15) as conv:
                await conv.send_message("/start")
                
                try:
                    await click_button_with_text(conv, "Add Account")
                    resp = await conv.get_response(timeout=10)
                except:
                    pass
                
                print("[*] Sending Phone Number...")
                await conv.send_message(clean_phone)
                
                try:
                    resp = await conv.get_response(timeout=10)
                    print(f"[*] Bot reply: {resp.text[:50]}")
                except Exception as e:
                    print(f"[!] Bot did not reply to number. Error: {e}")
                    await premium_cancel(order_id)
                    continue

                print("[*] Waiting for OTP from PremiumOTP...")
                start_time = time.time()
                otp_received = None
                
                while time.time() - start_time < 240:
                    status = await premium_get_status(order_id)
                    if status and status != "WAIT":
                        otp_received = status
                        break
                    await asyncio.sleep(6)
                
                if otp_received:
                    print(f"OTP RECEIVED: {otp_received} ! Sending to bot...")
                    await conv.send_message(otp_received)
                    try:
                        final_resp = await conv.get_response(timeout=15)
                        print(f"[*] Final Bot Reply: {final_resp.text[:100]}")
                    except:
                        pass
                else:
                    print("Timeout waiting for OTP. Canceling...")
                    await premium_cancel(order_id)
                    
        except Exception as e:
            print(f"[!] Telegram Conv Error: {e}")
            await premium_cancel(order_id)
            
        print("[*] Waiting 2s before next number...")
        await asyncio.sleep(2)

if __name__ == "__main__":
    if os.path.exists("ck_stop.flag"):
        os.remove("ck_stop.flag")
    asyncio.run(hunt_loop())