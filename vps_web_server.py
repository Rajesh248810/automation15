from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Union
import subprocess
import os
import json
import time
import requests

import sms_providers

app = FastAPI(title="Meesho Autonomous Multi-Provider Hunter Web Controller")

ADMIN_PIN = "224466"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

STATE_FILE = os.path.join(DATA_DIR, "hunter_state.json")
LOG_FILE = os.path.join(DATA_DIR, "hunter.log")
ACTIVE_ACTIVATIONS_FILE = os.path.join(DATA_DIR, "active_activations.json")
SUCCESS_FILE = os.path.join(DATA_DIR, "successful_accounts.json")
MARGIN_CONFIG_FILE = os.path.join(DATA_DIR, "margin_config.json")

class AuthRequest(BaseModel):
    pin: str

class StartRequest(BaseModel):
    count: int = 1
    provider: str = "otpdoctor"
    servers: Union[List[str], str] = []

class MarginRequest(BaseModel):
    margin: int

def verify_pin(pin: Optional[str]):
    if not pin or pin.strip() != ADMIN_PIN:
        raise HTTPException(status_code=401, detail="Invalid Admin Password")

def get_current_margin():
    if os.path.exists(MARGIN_CONFIG_FILE):
        try:
            with open(MARGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("margin", 45))
        except:
            pass
    return 45

def save_current_margin(val: int):
    try:
        with open(MARGIN_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"margin": val}, f, indent=2)
    except:
        pass

def get_hunter_pid():
    res = subprocess.run(["pgrep", "-f", "hunter_engine.py"], stdout=subprocess.PIPE, text=True)
    out = res.stdout.strip()
    return int(out.splitlines()[0]) if out else None

@app.post("/api/auth")
def auth(req: AuthRequest):
    if req.pin.strip() == ADMIN_PIN:
        return {"success": True, "token": ADMIN_PIN}
    return JSONResponse(status_code=401, content={"success": False, "error": "Incorrect PIN"})

@app.get("/api/status")
def get_status():
    pid = get_hunter_pid()
    state = {"status": "idle", "details": "Engine is standby", "target_count": 1, "completed_count": 0, "provider": "otpdoctor", "servers": "", "updated_at": 0}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except:
            pass
            
    balance_otpdoctor = sms_providers.get_otpdoctor_balance()
    balance_uotp = sms_providers.get_uotp_balance()
    balance_premiumotp = sms_providers.get_premiumotp_balance()
    current_margin = get_current_margin()

    active_sims = {}
    if os.path.exists(ACTIVE_ACTIVATIONS_FILE):
        try:
            with open(ACTIVE_ACTIVATIONS_FILE, "r", encoding="utf-8") as f:
                active_sims = json.load(f)
        except:
            pass

    successful_accounts = []
    if os.path.exists(SUCCESS_FILE):
        try:
            with open(SUCCESS_FILE, "r", encoding="utf-8") as f:
                successful_accounts = json.load(f)
        except:
            pass

    return {
        "running": pid is not None,
        "pid": pid,
        "state": state,
        "margin": current_margin,
        "balance_otpdoctor": balance_otpdoctor,
        "balance_uotp": balance_uotp,
        "balance_premiumotp": balance_premiumotp,
        "active_sims": active_sims,
        "successful_accounts": successful_accounts
    }

@app.get("/api/margin")
def get_margin():
    return {"margin": get_current_margin()}

@app.post("/api/margin")
def set_margin(req: MarginRequest, x_admin_pin: Optional[str] = Header(None)):
    verify_pin(x_admin_pin)
    val = max(0, req.margin)
    save_current_margin(val)
    return {"success": True, "margin": val, "message": f"Customer Price Margin updated to +₹{val}"}

@app.get("/api/logs")
def get_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return {"logs": lines[-120:]}
    return {"logs": []}

@app.post("/api/logs/clear")
def clear_logs(x_admin_pin: Optional[str] = Header(None)):
    verify_pin(x_admin_pin)
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
    return {"success": True, "message": "Logs cleared"}

@app.post("/api/start")
def start_hunter(req: StartRequest, x_admin_pin: Optional[str] = Header(None)):
    verify_pin(x_admin_pin)
    pid = get_hunter_pid()
    if pid is not None:
        return {"success": False, "error": f"Hunter is already running (PID: {pid})"}
    
    count = max(1, req.count)
    provider = req.provider.lower().strip()
    
    if isinstance(req.servers, list):
        servers_str = ",".join(req.servers)
    else:
        servers_str = str(req.servers)
    
    python_bin = os.path.join(BASE_DIR, "venv", "bin", "python3")
    if not os.path.exists(python_bin):
        python_bin = "python3"

    subprocess.Popen([python_bin, os.path.join(BASE_DIR, "hunter_engine.py"), str(count), provider, servers_str], cwd=BASE_DIR)
    return {"success": True, "message": f"Hunter started for {count} account(s) on {provider.upper()} (Priority Servers: {servers_str or 'All'})"}

@app.post("/api/stop")
def stop_hunter(x_admin_pin: Optional[str] = Header(None)):
    verify_pin(x_admin_pin)
    subprocess.run(["pkill", "-9", "-f", "hunter_engine.py"])
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": "stopped", "details": "Manually stopped by user", "updated_at": time.time()}, f)
    return {"success": True, "message": "Hunter engine stopped"}

@app.post("/api/emergency-cleanup")
def emergency_cleanup(x_admin_pin: Optional[str] = Header(None)):
    verify_pin(x_admin_pin)
    subprocess.run(["pkill", "-9", "-f", "hunter_engine.py"])
    acts = {}
    if os.path.exists(ACTIVE_ACTIVATIONS_FILE):
        try:
            with open(ACTIVE_ACTIVATIONS_FILE, "r", encoding="utf-8") as f:
                acts = json.load(f)
        except:
            pass

    cleaned = []
    for act_id, info in list(acts.items()):
        prov = info.get("provider", "OTPDoctor")
        sms_providers.cancel_activation(prov, act_id)
        cleaned.append(f"{info.get('phone')} ({prov})")

    if os.path.exists(ACTIVE_ACTIVATIONS_FILE):
        with open(ACTIVE_ACTIVATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

    return {"success": True, "output": f"Cancelled {len(cleaned)} active activations across OTPDoctor, uOTP & PremiumOTP: {', '.join(cleaned)}"}

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = os.path.join(BASE_DIR, "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Dashboard file not found</h1>"
