import os
from dotenv import load_dotenv
load_dotenv()

import requests
import json
import os
import re
import time

# Provider 1: OTPDoctor Active & Verified Working Servers
OTPDOCTOR_API_KEY = os.getenv("OTPDOCTOR_API_KEY", "")
OTPDOCTOR_BASE_URL = "https://www.otpdoctor.in/stubs/handler_api.php"

OTPDOCTOR_SERVERS = [
    {"id": "13915", "code": "inc", "name": "Meesho IN-C", "price": 8.0, "provider": "OTPDoctor"},
    {"id": "16487", "code": "m2_multi_in1", "name": "Meesho 2 MultiSms IN-1", "price": 8.5, "provider": "OTPDoctor"},
    {"id": "9318", "code": "multi_in1", "name": "MultiSms IN-1", "price": 8.5, "provider": "OTPDoctor"},
    {"id": "19826", "code": "in9", "name": "Meesho IN-9", "price": 9.0, "provider": "OTPDoctor"},
    {"id": "10619", "code": "multi_in3", "name": "MultiSms IN-3", "price": 9.5, "provider": "OTPDoctor"},
    {"id": "5655", "code": "multi_in6", "name": "MultiSms IN-6", "price": 9.5, "provider": "OTPDoctor"},
    {"id": "12752", "code": "in12", "name": "Meesho IN-12", "price": 11.0, "provider": "OTPDoctor"},
    {"id": "11642", "code": "m2_multi_in3", "name": "Meesho 2 MultiSms IN-3", "price": 11.5, "provider": "OTPDoctor"},
    {"id": "16040", "code": "multi_in2", "name": "MultiSms IN-2", "price": 12.0, "provider": "OTPDoctor"},
    {"id": "5841", "code": "in8", "name": "Meesho IN-8", "price": 12.0, "provider": "OTPDoctor"},
    {"id": "5797", "code": "meeso_unknown", "name": "Meeso Unknown Server", "price": 12.0, "provider": "OTPDoctor"},
    {"id": "20325", "code": "in14", "name": "Meesho IN-14", "price": 13.0, "provider": "OTPDoctor"},
    {"id": "20383", "code": "in11", "name": "Meesho IN-11", "price": 20.0, "provider": "OTPDoctor"}
]

# Provider 2: uOTP Complete Server Catalog
UOTP_API_KEY = os.getenv("UOTP_API_KEY", "")
UOTP_BASE_URL = "https://uotp.store/api/stubs/handler_api.php"

UOTP_SERVERS = [
    {"id": 2, "code": "uotp_2", "name": "Server 2", "provider": "uOTP"},
    {"id": 3, "code": "uotp_3", "name": "Server 3", "provider": "uOTP"},
    {"id": 4, "code": "uotp_4", "name": "Server 4", "provider": "uOTP"},
    {"id": 5, "code": "uotp_5", "name": "Server 5", "provider": "uOTP"},
    {"id": 6, "code": "uotp_6", "name": "Server 6", "provider": "uOTP"},
    {"id": 7, "code": "uotp_7", "name": "Server 7", "provider": "uOTP"},
    {"id": 8, "code": "uotp_8", "name": "Server 8", "provider": "uOTP"},
    {"id": 9, "code": "uotp_9", "name": "Server 9", "provider": "uOTP"},
    {"id": 10, "code": "uotp_10", "name": "Server 10", "provider": "uOTP"},
    {"id": 11, "code": "uotp_11", "name": "Server 11", "provider": "uOTP"},
    {"id": 12, "code": "uotp_12", "name": "Server 12", "provider": "uOTP"}
]

# Provider 3: PremiumOTP Complete Server Catalog
PREMIUMOTP_API_KEY = os.getenv("PREMIUMOTP_API_KEY", "")
PREMIUMOTP_BASE_URL = "https://premiumotp.pro/api/v1/stark"

PREMIUMOTP_SERVERS = [
    {"param": "India server 14", "code": "prem_in14", "name": "India Server 14", "price": 7.5, "provider": "PremiumOTP"},
    {"param": "India Server 11", "code": "prem_in11", "name": "India Server 11", "price": 8.0, "provider": "PremiumOTP"},
    {"param": "India Server 3", "code": "prem_in3", "name": "India Server 3", "price": 11.3, "provider": "PremiumOTP"},
    {"param": "India server 25", "code": "prem_in25", "name": "India Server 25", "price": 13.0, "provider": "PremiumOTP"},
    {"param": "India Server 19", "code": "prem_in19", "name": "India Server 19", "price": 20.0, "provider": "PremiumOTP"}
]

def get_otpdoctor_balance():
    for attempt in range(3):
        try:
            r = requests.get(f"{OTPDOCTOR_BASE_URL}?action=getBalance&api_key={OTPDOCTOR_API_KEY}", timeout=15)
            text = r.text.strip()
            if "ACCESS_BALANCE:" in text:
                val = text.split("ACCESS_BALANCE:")[1].strip()
                return float(val)
        except Exception:
            time.sleep(1)
    return None

def get_uotp_balance():
    for attempt in range(3):
        try:
            r = requests.get(f"{UOTP_BASE_URL}?action=getBalance&api_key={UOTP_API_KEY}", timeout=15)
            text = r.text.strip()
            if "ACCESS_BALANCE:" in text:
                val = text.split("ACCESS_BALANCE:")[1].strip()
                return float(val)
        except Exception:
            time.sleep(1)
    return None

def get_premiumotp_balance():
    for attempt in range(3):
        try:
            r = requests.get(f"{PREMIUMOTP_BASE_URL}?action=getBalance&api_key={PREMIUMOTP_API_KEY}", timeout=15)
            text = r.text.strip()
            if "ACCESS_BALANCE:" in text:
                val = text.split("ACCESS_BALANCE:")[1].strip()
                return float(val)
        except Exception:
            time.sleep(1)
    return None

def buy_number_otpdoctor(service_id, service_name="Meesho"):
    try:
        r = requests.get(f"{OTPDOCTOR_BASE_URL}?action=getNumber&api_key={OTPDOCTOR_API_KEY}&service={service_id}", timeout=15)
        text = r.text.strip()
        if "ACCESS_NUMBER:" in text:
            parts = text.split(":")
            activation_id = parts[1]
            phone = parts[2]
            phone_10 = phone[-10:] if len(phone) >= 10 else phone
            return activation_id, phone_10, f"OTPDoctor ({service_name})"
        return None, text, f"OTPDoctor ({service_name})"
    except Exception as e:
        return None, str(e), f"OTPDoctor ({service_name})"

def buy_number_uotp(server_id):
    try:
        url = f"{UOTP_BASE_URL}?action=getNumber&api_key={UOTP_API_KEY}&service=meesho&country=22&operator={server_id}"
        r = requests.get(url, timeout=15)
        text = r.text.strip()
        if "ACCESS_NUMBER:" in text:
            parts = text.split(":")
            activation_id = parts[1]
            phone = parts[2]
            phone_10 = phone[-10:] if len(phone) >= 10 else phone
            return activation_id, phone_10, f"uOTP (Srv {server_id})"
        return None, text, f"uOTP (Srv {server_id})"
    except Exception as e:
        return None, str(e), f"uOTP (Srv {server_id})"

def buy_number_premiumotp(server_param, server_name="India Srv"):
    try:
        url = f"{PREMIUMOTP_BASE_URL}?action=getNumber&api_key={PREMIUMOTP_API_KEY}&service=hp&server={server_param}"
        r = requests.get(url, timeout=15)
        text = r.text.strip()
        if "ACCESS_NUMBER:" in text:
            parts = text.split(":")
            activation_id = parts[1]
            phone = parts[2]
            phone_10 = phone[-10:] if len(phone) >= 10 else phone
            return activation_id, phone_10, f"PremiumOTP ({server_name})"
        return None, text, f"PremiumOTP ({server_name})"
    except Exception as e:
        return None, str(e), f"PremiumOTP ({server_name})"

def get_sms_status(provider_name, activation_id):
    p_lower = provider_name.lower()
    if "premiumotp" in p_lower:
        base_url = PREMIUMOTP_BASE_URL
        api_key = PREMIUMOTP_API_KEY
    elif "uotp" in p_lower:
        base_url = UOTP_BASE_URL
        api_key = UOTP_API_KEY
    else:
        base_url = OTPDOCTOR_BASE_URL
        api_key = OTPDOCTOR_API_KEY
    
    try:
        url = f"{base_url}?action=getStatus&api_key={api_key}&id={activation_id}"
        r = requests.get(url, timeout=12)
        text = r.text.strip()
        if "STATUS_OK:" in text:
            code_match = re.findall(r'\b\d{4,6}\b', text.split("STATUS_OK:")[1])
            return "OK", code_match[0] if code_match else text.split("STATUS_OK:")[1].strip()
        elif "STATUS_WAIT_CODE" in text or "STATUS_WAIT_RESEND" in text:
            return "WAIT", None
        elif "STATUS_CANCEL" in text or "ACCESS_CANCEL" in text:
            return "CANCELLED", None
        return text, None
    except Exception as e:
        return "ERROR", str(e)

def cancel_activation(provider_name, activation_id):
    p_lower = provider_name.lower()
    if "premiumotp" in p_lower:
        base_url = PREMIUMOTP_BASE_URL
        api_key = PREMIUMOTP_API_KEY
    elif "uotp" in p_lower:
        base_url = UOTP_BASE_URL
        api_key = UOTP_API_KEY
    else:
        base_url = OTPDOCTOR_BASE_URL
        api_key = OTPDOCTOR_API_KEY
    
    try:
        url = f"{base_url}?action=setStatus&api_key={api_key}&id={activation_id}&status=8"
        r = requests.get(url, timeout=12)
        res = r.text.strip()
        if "STATUS_CANCEL" in res or "ACCESS_CANCEL" in res:
            return "CANCELLED", 0
        elif "WAIT_CANCEL:" in res:
            wait_sec = int(res.split("WAIT_CANCEL:")[1])
            return "WAIT", wait_sec
        elif "EARLY_CANCEL_DENIED" in res:
            return "WAIT", 130
        return res, 0
    except Exception as e:
        return "ERROR", 0

def complete_activation(provider_name, activation_id):
    p_lower = provider_name.lower()
    if "premiumotp" in p_lower:
        base_url = PREMIUMOTP_BASE_URL
        api_key = PREMIUMOTP_API_KEY
    elif "uotp" in p_lower:
        base_url = UOTP_BASE_URL
        api_key = UOTP_API_KEY
    else:
        base_url = OTPDOCTOR_BASE_URL
        api_key = OTPDOCTOR_API_KEY
    try:
        requests.get(f"{base_url}?action=setStatus&api_key={api_key}&id={activation_id}&status=6", timeout=12)
    except:
        pass
