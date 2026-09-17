from dotenv import load_dotenv
load_dotenv()
import asyncio, requests, urllib.parse, json, os, time
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest

API_ID = int(os.getenv("TELEGRAM_API_ID", "2040"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME = '/root/meesho_otp_hunter/meesho_user_session'
MINIAPP_BASE_URL = 'https://meeshoshop.146.56.48.72.nip.io'
WEBAPP_BASE_URL = 'os.getenv("WEBAPP_BASE_URL", "https://pricetrackerpro.fojadomain.fun")'
WEBAPP_TOKEN = os.getenv("WEBAPP_TOKEN", "")
DATA_DIR = '/root/meesho_otp_hunter/data'

headers_webapp = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/json',
    'x-token': WEBAPP_TOKEN
}

async def sync_all_missing():
    print("=" * 60)
    print("🚀 STARTING AUTOMATED ACCOUNT SYNC FROM MeeshoOrderBot TO WEBAPP")
    print("=" * 60)

    # 1. Fetch webapp accounts
    r_web = requests.get(f'{WEBAPP_BASE_URL}/api/accounts', headers=headers_webapp, timeout=15)
    webapp_accounts = r_web.json().get('accounts', [])
    webapp_phones = set()
    for a in webapp_accounts:
        p = str(a.get('phone', '')).replace('+91', '').replace('+', '').strip()
        if p:
            webapp_phones.add(p)
            
    print(f"[*] Current WebApp Accounts: {len(webapp_phones)}")

    # 2. Connect Telethon & Open Mini App
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    bot_entity = await client.get_entity('MeeshoOrderBot')
    
    res = await client(RequestWebViewRequest(
        peer=bot_entity,
        bot=bot_entity,
        url=f"{MINIAPP_BASE_URL}/?view=manage",
        platform="android"
    ))
    
    parsed_url = urllib.parse.urlparse(res.url)
    params = urllib.parse.parse_qs(parsed_url.fragment)
    tg_init_data = params.get("tgWebAppData", [""])[0]
    
    headers_miniapp = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 16; Pixel 10) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "X-Tg-Init-Data": tg_init_data
    }
    
    r_list = requests.get(f"{MINIAPP_BASE_URL}/api/accounts/list", headers=headers_miniapp, timeout=15)
    miniapp_accounts = r_list.json().get("accounts", [])
    print(f"[*] Total MeeshoOrderBot Accounts: {len(miniapp_accounts)}")
    
    missing_accounts = []
    for acc in miniapp_accounts:
        mob = str(acc.get('mobile', '')).replace('+91', '').replace('+', '').strip()
        if mob and mob not in webapp_phones:
            missing_accounts.append(acc)
            
    print(f"[*] Total Missing Accounts to Export & Import: {len(missing_accounts)}\n")
    
    success_count = 0
    fail_count = 0
    
    for i, acc in enumerate(missing_accounts, 1):
        acc_id = acc.get('id')
        mobile = str(acc.get('mobile', '')).strip()
        print(f"[{i}/{len(missing_accounts)}] Processing Account {acc_id} (+91 {mobile})...")
        
        try:
            # Select account in Mini App
            r_sel = requests.post(f"{MINIAPP_BASE_URL}/api/accounts/select", headers=headers_miniapp, json={"account_id": acc_id}, timeout=15)
            # Export session file to chat
            r_exp = requests.post(f"{MINIAPP_BASE_URL}/api/account/export_file", headers=headers_miniapp, timeout=15)
            
            # Wait for file in chat
            downloaded_file = None
            for _ in range(12):
                await asyncio.sleep(1.5)
                msgs = await client.get_messages(bot_entity, limit=5)
                for m in msgs:
                    if m.file and m.file.name and m.file.name.endswith(".json"):
                        fname = m.file.name
                        if str(mobile) in fname or str(acc_id) in fname:
                            local_path = os.path.join(DATA_DIR, fname)
                            await client.download_media(m.media, file=local_path)
                            downloaded_file = local_path
                            break
                if downloaded_file:
                    break
                    
            if not downloaded_file or not os.path.exists(downloaded_file):
                print(f"  [!] Failed to download session file for +91 {mobile}")
                fail_count += 1
                continue
                
            # Read session JSON
            with open(downloaded_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
                
            # Import into WebApp
            r_imp = requests.post(f"{WEBAPP_BASE_URL}/api/import", headers=headers_webapp, json={"data": session_data}, timeout=15)
            imp_res = r_imp.json()
            
            if imp_res.get('ok'):
                print(f"  ✅ [SUCCESS] +91 {mobile} imported successfully into WebApp!")
                success_count += 1
                # Clean up local file
                try:
                    os.remove(downloaded_file)
                except:
                    pass
            else:
                print(f"  [!] Import API error for +91 {mobile}: {imp_res.get('error')}")
                fail_count += 1
                
        except Exception as e:
            print(f"  [!] Exception syncing +91 {mobile}: {e}")
            fail_count += 1
            
        await asyncio.sleep(1)

    print("\n" + "=" * 60)
    print(f"🎉 SYNC COMPLETED: {success_count} Imported Successfully, {fail_count} Failed.")
    print("=" * 60)
    
    await client.disconnect()

asyncio.run(sync_all_missing())
