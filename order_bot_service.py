DEFAULT_REFERRAL_LINK = "https://app.meesho.com/2yoV/r99th0qd?via=4bhsf7&from=MAIN"
DEFAULT_REFERRAL_CODE = "4bhsf7"
"""
order_bot_service.py
────────────────────
Standalone SaaS Backend for Meesho Order Bot Mini-App.
Endpoints:
  - Account & Session Management: Import session, list accounts, switch account, verify token.
  - Device Spoofer: Rotate Android ID/GAID for ₹125 new-user discount offer.
  - Catalog: Search, Parse Product Link, Size Selector, Customer Reviews.
  - Cart: Add with Size, View Cart, Delete.
  - Address: Get Addresses, Add New Address, Modify Order Address.
  - Checkout (Approach 2): Generate instant GPay/PhonePe UPI Link & Live Dynamic QR Code.
  - Orders: Live Order History, Tracking, Cancel Order.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import json
import uuid

from meesho_core_engine import MeeshoEngine

app = FastAPI(title="Meesho Order Bot SaaS API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "data", "harvested_accounts.json")
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# ── Multi-Account Storage Helper ──────────────────────────────────────────────
def load_all_accounts() -> list:
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback to local session file if available
    default_acc = os.getenv("DEFAULT_ACCOUNT_FILE", "meesho_account.json")
    acc_file = os.path.join(BASE_DIR, default_acc)
    if os.path.exists(acc_file):
        try:
            with open(acc_file, "r", encoding="utf-8") as f:
                return [json.load(f)]
        except Exception:
            pass
    return []

def save_all_accounts(accs: list):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accs, f, indent=2)

# Global active engine instance
current_accounts = load_all_accounts()
active_session = current_accounts[0] if current_accounts else {}
engine = MeeshoEngine(active_session)

# ── Pydantic Request Models ───────────────────────────────────────────────────
class ImportSessionRequest(BaseModel):
    session_json: str

class SwitchAccountRequest(BaseModel):
    phone: str

class SearchRequest(BaseModel):
    query: Optional[str] = "trending"
    page: Optional[int] = 1

class ProductLinkRequest(BaseModel):
    link: str

class AddCartRequest(BaseModel):
    product_id: str
    variation_id: Optional[str] = "167"
    quantity: Optional[int] = 1

class AddAddressRequest(BaseModel):
    name: str
    phone: str
    house: str
    street: str
    city: str
    state: str
    pincode: str

class ChangeAddressRequest(BaseModel):
    order_id: str
    new_address_id: str

class CheckoutRequest(BaseModel):
    cart_id: Optional[str] = None
    address_id: Optional[str] = None
    amount: Optional[float] = 99.0

class CancelOrderRequest(BaseModel):
    order_id: str
    reason: Optional[str] = "Ordered by mistake"

# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "online",
        "service": "Meesho Order Bot SaaS",
        "active_phone": engine.session.get("phone", "None"),
        "engine_target": "prod.meeshoapi.com"
    }

# ── Accounts & Sessions ──
@app.get("/api/accounts")
def list_accounts():
    accs = load_all_accounts()
    active_p = engine.session.get("phone", "")
    return {
        "accounts": [
            {
                "phone": a.get("phone", a.get("mobile", "Unknown")),
                "user_id": a.get("user_id"),
                "is_active": (a.get("phone") == active_p or a.get("mobile") == active_p),
                "device": f"{a.get('identity', {}).get('make', '')} {a.get('identity', {}).get('model', '')}"
            }
            for a in accs
        ],
        "count": len(accs)
    }

@app.post("/api/accounts/import")
def import_session(req: ImportSessionRequest):
    global engine
    try:
        data = json.loads(req.session_json.strip())
        accs = load_all_accounts()
        phone = data.get("phone") or data.get("mobile") or f"+91{uuid.uuid4().hex[:10]}"
        data["phone"] = phone
        # Update or append
        existing = [a for a in accs if a.get("phone") != phone]
        existing.insert(0, data)
        save_all_accounts(existing)
        engine = MeeshoEngine(data)
        return {"ok": True, "message": f"Account {phone} imported successfully & activated!", "account": data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

@app.post("/api/accounts/switch")
def switch_account(req: SwitchAccountRequest):
    global engine
    accs = load_all_accounts()
    for a in accs:
        if a.get("phone") == req.phone or a.get("mobile") == req.phone:
            engine = MeeshoEngine(a)
            return {"ok": True, "active_phone": req.phone, "message": f"Switched to {req.phone}"}
    raise HTTPException(status_code=404, detail="Account not found in vault")

@app.get("/api/accounts/verify")
def verify_account():
    return engine.verify_session()

@app.post("/api/device/rotate")
def rotate_device_environment():
    """Spoofs fresh Android ID and GAID to claim ₹125/₹125 new-user first-order discounts."""
    new_ident = engine.rotate_android_device()
    # Save back to active accounts file
    accs = load_all_accounts()
    for a in accs:
        if a.get("phone") == engine.session.get("phone"):
            a["identity"] = new_ident
            a["instance_id"] = new_ident["instance_id"]
            a["gaid"] = new_ident["gaid"]
            break
    save_all_accounts(accs)
    return {
        "ok": True,
        "message": "Android Environment Rotated! Claiming fresh ₹125 first-order discount.",
        "new_device": f"{new_ident['make']} {new_ident['model']}",
        "new_android_id": new_ident["android_id"]
    }

# ── Catalog & Search ──
@app.post("/api/catalog/search")
def search_catalog(req: SearchRequest):
    results = engine.search(query=req.query, page=req.page or 1)
    return {"ok": True, "items": results, "count": len(results)}

@app.post("/api/catalog/product")
def get_product(req: ProductLinkRequest):
    product = engine.parse_product_link(req.link)
    return {"ok": True, "product": product}

# ── Cart ──
@app.get("/api/cart")
def view_cart():
    cart = engine.get_cart()
    return {"ok": True, "cart": cart}

@app.post("/api/cart/add")
def add_cart(req: AddCartRequest):
    res = engine.add_to_cart(product_id=req.product_id, variation_id=req.variation_id, quantity=req.quantity)
    return {"ok": res.get("success", False), "data": res.get("data")}

@app.delete("/api/cart/item/{item_id}")
def delete_cart_item(item_id: str):
    res = engine.remove_cart_item(item_id)
    return {"ok": res.get("success", False)}

# ── Addresses ──
@app.get("/api/addresses")
def get_addresses():
    addrs = engine.get_addresses()
    return {"ok": True, "addresses": addrs}

@app.post("/api/addresses/add")
def add_address(req: AddAddressRequest):
    res = engine.add_address(req.dict())
    return {"ok": res.get("success", False), "address_id": res.get("address_id")}

@app.post("/api/orders/change-address")
def change_order_address(req: ChangeAddressRequest):
    res = engine.update_order_address(req.order_id, req.new_address_id)
    return {"ok": res.get("success", False), "data": res.get("data")}

# ── Checkout & UPI Payment Engine (Approach 2) ──
@app.post("/api/checkout/initiate")
def initiate_payment(req: CheckoutRequest):
    """
    Generates dynamic UPI Intent link and QR Code.
    The customer clicks the link to open GPay/PhonePe or scans the QR.
    """
    res = engine.initiate_checkout(cart_id=req.cart_id, address_id=req.address_id, amount=req.amount or 99.0)
    return {"ok": True, "checkout": res}

# ── Orders & Tracking ──
@app.get("/api/orders")
def list_orders():
    orders = engine.get_orders()
    return {"ok": True, "orders": orders}

@app.post("/api/orders/cancel")
def cancel_order(req: CancelOrderRequest):
    res = engine.cancel_order(req.order_id, req.reason or "Ordered by mistake")
    return {"ok": res.get("success", False), "data": res.get("data")}

# ── Static UI mount ──
STATIC_DIR = os.path.join(BASE_DIR, "order_bot_web")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
