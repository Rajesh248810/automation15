from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import json
import os
import re

app = FastAPI(title="Meesho Customer Price & Product Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
MARGIN_CONFIG_FILE = os.path.join(DATA_DIR, "margin_config.json")

WEBAPP_BASE_URL = "https://pricetrackerpro.fojadomain.fun"
WEBAPP_TOKEN = "1729719181.5053a8bd2706f61b"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "x-token": WEBAPP_TOKEN
}

class ProductCheckRequest(BaseModel):
    link: str

def get_current_margin():
    if os.path.exists(MARGIN_CONFIG_FILE):
        try:
            with open(MARGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("margin", 45))
        except:
            pass
    return 45

def get_fresh_account_phone():
    try:
        r = requests.get(f"{WEBAPP_BASE_URL}/api/accounts", headers=headers, timeout=10)
        data = r.json()
        accounts = data.get("accounts", [])
        
        # Priority 1: Unused fresh accounts (no orders placed)
        fresh = [a.get("phone") for a in accounts if not a.get("placed", False) and not a.get("order_num")]
        if fresh:
            return fresh[0]
            
        # Priority 2: Any available active account
        if accounts:
            return accounts[0].get("phone")
    except Exception as e:
        print("[!] Error fetching accounts:", e)
    return "+919305055373"

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Meesho Customer Price Viewer", "margin": get_current_margin()}

@app.get("/api/margin")
def get_margin():
    return {"margin": get_current_margin()}

@app.post("/api/check-price")
def check_price(req: ProductCheckRequest):
    link = req.link.strip()
    if not link:
        raise HTTPException(status_code=400, detail="Product link is required")

    phone = get_fresh_account_phone()
    margin = get_current_margin()
    print(f"[*] Checking price for link using Account {phone} (Margin: +Rs.{margin}): {link}")

    try:
        r = requests.post(f"{WEBAPP_BASE_URL}/api/product", headers=headers, json={
            "phone": phone,
            "link": link
        }, timeout=25)
        
        data = r.json()
        if not data.get("ok"):
            error_msg = data.get("error", "Failed to fetch product details. Please check the link.")
            return JSONResponse(status_code=400, content={"ok": False, "error": error_msg})

        prod = data.get("product", {})
        
        # Original Prices
        base_upi = prod.get("upi", 0)
        base_cod = prod.get("cod", 0)
        mrp = prod.get("mrp", 0)
        
        # Dynamic Margin Added on UPI & COD
        customer_upi = base_upi + margin if base_upi > 0 else 0
        customer_cod = base_cod + margin if base_cod > 0 else 0

        # Build modified variations with dynamic margin
        variations = []
        for v in prod.get("variations", []):
            v_upi = v.get("upi", base_upi)
            v_cod = v.get("cod", base_cod)
            variations.append({
                "id": v.get("id"),
                "name": v.get("name", "Free Size"),
                "mrp": v.get("mrp", mrp),
                "original_upi": v_upi,
                "customer_upi": v_upi + margin if v_upi > 0 else 0,
                "customer_cod": v_cod + margin if v_cod > 0 else 0,
                "in_stock": v.get("in_stock", True)
            })

        return {
            "ok": True,
            "account_used": phone,
            "product": {
                "id": prod.get("id"),
                "name": prod.get("name"),
                "supplier": prod.get("supplier", "Verified Supplier"),
                "mrp": mrp,
                "original_upi": base_upi,
                "customer_upi": customer_upi,
                "customer_cod": customer_cod,
                "margin_added": margin,
                "in_stock": prod.get("in_stock", True),
                "fod_value": prod.get("fod_value", 0),
                "fod_text": prod.get("fod_text", ""),
                "images": prod.get("images", []),
                "promos": prod.get("promos", []),
                "variations": variations
            }
        }
    except Exception as e:
        print("[!] Check price exception:", e)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.get("/", response_class=HTMLResponse)
def serve_home():
    html_path = os.path.join(BASE_DIR, "price_checker_index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Price Checker UI Not Found</h1>"
