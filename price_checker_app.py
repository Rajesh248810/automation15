try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import requests
import json
import os
import re
import time
import concurrent.futures
import threading

app = FastAPI(title="Meesho Customer Hub")

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
ORDERS_CACHE_FILE = os.path.join(DATA_DIR, "orders_enriched_cache.json")
ZIP_PATH = os.path.join(BASE_DIR, "meesho_hub_portable.zip")
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")
SW_PATH = os.path.join(BASE_DIR, "sw.js")

WEBAPP_BASE_URL = os.getenv("WEBAPP_BASE_URL", "https://pricetrackerpro.fojadomain.fun")
WEBAPP_TOKEN = os.getenv("WEBAPP_TOKEN", "1729719181.5053a8bd2706f61b")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "x-token": WEBAPP_TOKEN
}

# Helper to convert numeric Meesho PID to official base36 shortcode link
def pid_to_meesho_url(pid):
    if not pid:
        return ""
    try:
        num = int(pid)
        chars = "0123456789abcdefghijklmnopqrstuvwxyz"
        res = ""
        while num > 0:
            res = chars[num % 36] + res
            num //= 36
        return f"https://www.meesho.com/s/p/{res}"
    except:
        return f"https://www.meesho.com/s/p/{pid}"

# In-memory fast cache for orders
order_details_cache = {}
if os.path.exists(ORDERS_CACHE_FILE):
    try:
        with open(ORDERS_CACHE_FILE, "r", encoding="utf-8") as f:
            order_details_cache = json.load(f)
    except:
        order_details_cache = {}

def save_order_details_cache():
    try:
        with open(ORDERS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(order_details_cache, f, indent=2, ensure_ascii=False)
    except:
        pass

def safe_num(val, default=0):
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except:
        return default

class ProductCheckRequest(BaseModel):
    link: str

class ProductSearchRequest(BaseModel):
    query: str
    cursor: Optional[str] = None
    search_session_id: Optional[str] = None

def get_current_margin():
    if os.path.exists(MARGIN_CONFIG_FILE):
        try:
            with open(MARGIN_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("margin", 55))
        except:
            pass
    return 55

# Dynamic Fresh FOD Account Selector
# Strictly uses active 100% verified ₹120 OFF accounts created by Hunter Engine
cached_best_account = {"phone": None, "updated_at": 0}

def get_fresh_account_phone():
    now = time.time()
    if cached_best_account["phone"] and (now - cached_best_account["updated_at"] < 120):
        return cached_best_account["phone"]

    # 1. Fetch recently hunted 120 OFF accounts from successful_accounts.json
    succ_file = os.path.join(DATA_DIR, "successful_accounts.json")
    hunted_120_phones = []
    if os.path.exists(succ_file):
        try:
            with open(succ_file, "r", encoding="utf-8") as f:
                succ = json.load(f)
                for s in reversed(succ):
                    p = str(s.get("phone", "")).replace("+91", "").strip()
                    if p:
                        hunted_120_phones.append(f"+91{p}")
        except Exception:
            pass

    # Strictly exclude old 135 OFF account
    EXCLUDED_ACCOUNTS = set()

    try:
        r = requests.get(f"{WEBAPP_BASE_URL}/api/accounts", headers=headers, timeout=6)
        data = r.json()
        accounts = data.get("accounts", [])
        
        unplaced = [a.get("phone") for a in accounts if not a.get("placed", False) and not a.get("order_num") and a.get("phone") not in EXCLUDED_ACCOUNTS]
        
        # Match unplaced accounts with hunted 120 OFF accounts first
        for p in hunted_120_phones:
            if p in unplaced and p not in EXCLUDED_ACCOUNTS:
                cached_best_account["phone"] = p
                cached_best_account["updated_at"] = now
                return p
                
        # If any other unplaced account exists
        for p in unplaced:
            if p not in EXCLUDED_ACCOUNTS:
                cached_best_account["phone"] = p
                cached_best_account["updated_at"] = now
                return p

        # Fallback to any active hunted 120 OFF phone
        for p in hunted_120_phones:
            if p not in EXCLUDED_ACCOUNTS:
                cached_best_account["phone"] = p
                cached_best_account["updated_at"] = now
                return p

        for a in accounts:
            p = a.get("phone")
            if p and p not in EXCLUDED_ACCOUNTS:
                cached_best_account["phone"] = p
                cached_best_account["updated_at"] = now
                return p
    except Exception as e:
        print("[!] Error fetching accounts:", e)
        
    fallback = hunted_120_phones[0] if hunted_120_phones else None
    cached_best_account["phone"] = fallback
    cached_best_account["updated_at"] = now
    return fallback

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Meesho Customer Price, Search & Order Viewer", "margin": get_current_margin(), "active_account": get_fresh_account_phone()}

@app.get("/api/margin")
def get_margin():
    return {"margin": get_current_margin()}

@app.get("/manifest.json")
def get_manifest():
    if os.path.exists(MANIFEST_PATH):
        return FileResponse(MANIFEST_PATH, media_type="application/json")
    return JSONResponse(status_code=404, content={"error": "Not found"})

@app.get("/sw.js")
def get_sw():
    if os.path.exists(SW_PATH):
        return FileResponse(SW_PATH, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"error": "Not found"})

# ----------------- 0. DOWNLOAD PORTABLE WEB APP ZIP -----------------
@app.get("/download")
@app.get("/api/download-app")
def download_portable_app():
    if os.path.exists(ZIP_PATH):
        return FileResponse(
            path=ZIP_PATH,
            filename="meesho_hub_portable.zip",
            media_type="application/zip"
        )
    raise HTTPException(status_code=404, detail="Portable app package not found")

# ----------------- 1. AUTOCOMPLETE / SEARCH SUGGESTIONS -----------------
@app.get("/api/search/suggestions")
def get_search_suggestions(q: str = Query("", description="Prefix text")):
    query = q.strip()
    if not query:
        return {"ok": True, "suggestions": []}

    phone = get_fresh_account_phone()
    try:
        r = requests.post(f"{WEBAPP_BASE_URL}/api/search/suggest", headers=headers, json={
            "q": query,
            "phone": phone
        }, timeout=6)
        data = r.json()
        suggestions = data.get("suggestions", [])
        return {"ok": True, "query": query, "suggestions": suggestions}
    except Exception as e:
        print("[!] Suggestion error:", e)
        return {"ok": True, "suggestions": []}

# ----------------- 2. PRODUCT SEARCH ENDPOINT (100% MATCHED OFFER PRICES + ADMIN MARGIN) -----------------
@app.post("/api/search-products")
def search_products(req: ProductSearchRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query is required")

    phone = get_fresh_account_phone()
    margin = get_current_margin()

    payload = {
        "query": query,
        "phone": phone
    }
    if req.cursor:
        payload["cursor"] = req.cursor
    if req.search_session_id:
        payload["search_session_id"] = req.search_session_id

    try:
        r = requests.post(f"{WEBAPP_BASE_URL}/api/search", headers=headers, json=payload, timeout=25)
        data = r.json()
        
        if not data.get("ok"):
            error_msg = data.get("error", "Search failed. Please try again.")
            return JSONResponse(status_code=400, content={"ok": False, "error": error_msg})

        raw_items = data.get("items", [])
        clean_items = []

        for it in raw_items:
            pid = it.get("pid")
            base_cod = safe_num(it.get("price"), 0)
            base_upi = safe_num(it.get("upi"), base_cod)
            raw_mrp = safe_num(it.get("mrp"), 0)
            
            # Exact Live Offer Deal Prices + Admin Margin
            customer_upi = base_upi + margin if base_upi > 0 else (base_cod + margin)
            customer_cod = base_cod + margin if base_cod > 0 else customer_upi

            mrp = raw_mrp
            if mrp <= 0 or mrp <= customer_cod:
                mrp = customer_cod + 250

            discount_text = it.get("discount_text") or "Upto ₹120 OFF"

            clean_items.append({
                "pid": pid,
                "catalog_id": it.get("catalog_id"),
                "name": it.get("name", "Meesho Product"),
                "image": it.get("image", ""),
                "original_upi": base_upi,
                "original_cod": base_cod,
                "customer_upi": customer_upi,
                "customer_cod": customer_cod,
                "mrp": mrp,
                "margin_added": margin,
                "discount_text": discount_text,
                "link": pid_to_meesho_url(pid),
                "supplier_id": it.get("supplier_id"),
                "mall": bool(it.get("mall") or it.get("is_mall"))
            })

        next_cursor = data.get("cursor")
        next_session_id = data.get("search_session_id")
        has_more = bool(next_cursor and len(clean_items) > 0)

        return {
            "ok": True,
            "query": query,
            "account_used": phone,
            "margin_applied": margin,
            "total_fetched": len(clean_items),
            "items": clean_items,
            "cursor": next_cursor,
            "search_session_id": next_session_id,
            "has_more": has_more
        }
    except Exception as e:
        print("[!] Search products exception:", e)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# ----------------- 3. PRICE CHECK BY LINK / PID (100% MATCHED LIVE OFFER PRICES) -----------------
@app.post("/api/check-price")
def check_price(req: ProductCheckRequest):
    link = req.link.strip()
    if not link:
        raise HTTPException(status_code=400, detail="Product link is required")

    phone = get_fresh_account_phone()
    margin = get_current_margin()

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
        pid = prod.get("id")
        base_upi = safe_num(prod.get("upi"), 0)
        base_cod = safe_num(prod.get("cod"), 0)
        raw_mrp = safe_num(prod.get("mrp"), 0)
        fod_value = safe_num(prod.get("fod_value"), 0)
        fod_text = prod.get("fod_text", "")

        customer_upi = base_upi + margin if base_upi > 0 else (base_cod + margin)
        customer_cod = base_cod + margin if base_cod > 0 else customer_upi
        mrp = raw_mrp if raw_mrp > customer_cod else (customer_cod + 250)

        images = prod.get("images", [])
        if not images and prod.get("image"):
            images = [prod.get("image")]

        variations = []
        for v in prod.get("variations", []):
            v_upi = safe_num(v.get("upi"), base_upi)
            v_cod = safe_num(v.get("cod"), base_cod)
            v_mrp = safe_num(v.get("mrp"), mrp)
            variations.append({
                "id": v.get("id"),
                "name": v.get("name", "Free Size"),
                "mrp": v_mrp,
                "original_upi": v_upi,
                "customer_upi": v_upi + margin if v_upi > 0 else customer_upi,
                "customer_cod": v_cod + margin if v_cod > 0 else customer_cod,
                "in_stock": v.get("in_stock", True)
            })

        meesho_official_link = pid_to_meesho_url(pid) if pid else link

        return {
            "ok": True,
            "account_used": phone,
            "product": {
                "id": pid,
                "name": prod.get("name"),
                "supplier": prod.get("supplier", "Verified Supplier"),
                "mall": bool(prod.get("mall") or prod.get("is_mall")),
                "brand": prod.get("brand", ""),
                "mrp": mrp,
                "original_upi": base_upi,
                "customer_upi": customer_upi,
                "customer_cod": customer_cod,
                "margin_added": margin,
                "in_stock": prod.get("in_stock", True),
                "fod_value": fod_value,
                "fod_text": fod_text or (f"₹{fod_value} OFF" if fod_value > 0 else "Special Deal Applied"),
                "images": images,
                "link": meesho_official_link,
                "promos": prod.get("promos", []),
                "variations": variations
            }
        }
    except Exception as e:
        print("[!] Check price exception:", e)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# Helper to fetch single order detail and extract delivery address mobile
def fetch_order_address_sync(order_num):
    if order_num in order_details_cache:
        cached = order_details_cache[order_num]
        if cached.get("delivery_mobile") or cached.get("no_account"):
            return cached

    try:
        r = requests.get(f"{WEBAPP_BASE_URL}/api/orders/{order_num}", headers=headers, timeout=5)
        data = r.json()
        if data.get("ok"):
            d = data.get("detail", {})
            addr = d.get("address", {})
            info = {
                "delivery_mobile": str(addr.get("mobile", "")).strip(),
                "delivery_name": str(addr.get("name", "")).strip(),
                "city": str(addr.get("city", "")).strip(),
                "state": str(addr.get("state", "")).strip(),
                "pin": str(addr.get("pin", "")).strip(),
                "courier": str(d.get("courier", "")).strip(),
                "awb": str(d.get("awb", "")).strip(),
                "no_account": False,
                "updated_at": time.time()
            }
            order_details_cache[order_num] = info
            return info
        else:
            info = {
                "no_account": True,
                "error": data.get("error", "No account available"),
                "updated_at": time.time()
            }
            order_details_cache[order_num] = info
            return info
    except:
        pass
    return {}

# ----------------- 4. ALL ORDERS ENDPOINT (WITH DELIVERY ADDRESS & NO PRICES) -----------------
@app.get("/api/orders/all")
def get_all_orders(refresh: bool = False):
    try:
        raw_orders = []
        seen_order_nums = set()
        offset = 0
        max_pages = 25
        
        for _ in range(max_pages):
            params = {"offset": offset}
            if refresh:
                params["refresh"] = "true"
            r = requests.get(f"{WEBAPP_BASE_URL}/api/orders/all", headers=headers, params=params, timeout=20)
            data = r.json()
            if not data.get("ok"):
                if not raw_orders:
                    return JSONResponse(status_code=400, content={"ok": False, "error": data.get("error", "Failed to fetch orders")})
                break
            
            page_orders = data.get("orders", [])
            for o in page_orders:
                # Remove products which have no tracking or no account
                status_str = str(o.get("status") or "").strip().lower()
                stage_key = str(o.get("stage_key") or "").strip().lower()
                if not stage_key or stage_key in ["none", "removed", ""] or "no tracking" in status_str or "removed" in status_str:
                    continue

                onum = o.get("order_num")
                if onum and onum not in seen_order_nums:
                    seen_order_nums.add(onum)
                    raw_orders.append(o)
                elif not onum:
                    raw_orders.append(o)
                    
            next_offset = data.get("next_offset")
            if next_offset is not None and next_offset != offset and page_orders:
                offset = next_offset
            else:
                break
        order_nums = [o.get("order_num") for o in raw_orders if o.get("order_num")]

        missing = [on for on in order_nums if on not in order_details_cache or (not order_details_cache[on].get("delivery_mobile") and not order_details_cache[on].get("no_account"))]
        if missing:
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                list(executor.map(fetch_order_address_sync, missing))
            save_order_details_cache()

        clean_orders = []
        for o in raw_orders:
            onum = o.get("order_num")
            cached_addr = order_details_cache.get(onum, {})
            if cached_addr.get("no_account"):
                continue

            status_str = str(o.get("status") or "Ordered").strip()
            stage_key = str(o.get("stage_key") or "").strip().lower()
            if not stage_key or stage_key in ["none", "removed", ""]:
                continue

            clean_orders.append({
                "order_num": onum,
                "status": o.get("status", "Ordered"),
                "stage_key": stage_key,
                "phone": o.get("phone", ""),
                "delivery_mobile": cached_addr.get("delivery_mobile", ""),
                "delivery_name": cached_addr.get("delivery_name", ""),
                "city": cached_addr.get("city", ""),
                "state": cached_addr.get("state", ""),
                "pin": cached_addr.get("pin", ""),
                "product": o.get("product", "Meesho Product"),
                "image": o.get("image", ""),
                "created": o.get("created"),
                "eta": o.get("eta")
            })

        return {
            "ok": True,
            "total_orders": len(clean_orders),
            "orders": clean_orders
        }
    except Exception as e:
        print("[!] Get all orders error:", e)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

# ----------------- 5. ORDER DETAIL & TRACKING ENDPOINT (NO PRICES) -----------------
@app.get("/api/orders/detail")
def get_order_detail(order_num: str = Query(..., description="Order Number")):
    order_num = order_num.strip()
    if not order_num:
        raise HTTPException(status_code=400, detail="Order number is required")

    try:
        r = requests.get(f"{WEBAPP_BASE_URL}/api/orders/{order_num}", headers=headers, timeout=20)
        data = r.json()
        if not data.get("ok"):
            order_details_cache[order_num] = {
                "no_account": True,
                "error": data.get("error", "No account available"),
                "updated_at": time.time()
            }
            save_order_details_cache()
            return JSONResponse(status_code=400, content={"ok": False, "error": data.get("error", "Order detail not found")})

        raw_detail = data.get("detail", {})
        raw_product = raw_detail.get("product", {})
        raw_addr = raw_detail.get("address", {})
        
        order_details_cache[order_num] = {
            "delivery_mobile": str(raw_addr.get("mobile", "")).strip(),
            "delivery_name": str(raw_addr.get("name", "")).strip(),
            "city": str(raw_addr.get("city", "")).strip(),
            "state": str(raw_addr.get("state", "")).strip(),
            "pin": str(raw_addr.get("pin", "")).strip(),
            "courier": str(raw_detail.get("courier", "")).strip(),
            "awb": str(raw_detail.get("awb", "")).strip(),
            "updated_at": time.time()
        }
        
        clean_product = {
            "name": raw_product.get("name", "Meesho Product"),
            "size": raw_product.get("size", "Free Size"),
            "quantity": raw_product.get("quantity", 1),
            "image": raw_product.get("image", "")
        }

        clean_detail = {
            "order_num": raw_detail.get("order_num"),
            "sub_order_num": raw_detail.get("sub_order_num"),
            "order_date": raw_detail.get("order_date"),
            "product": clean_product,
            "status_title": raw_detail.get("status_title", "Ordered"),
            "status_sub": raw_detail.get("status_sub", ""),
            "status_date": raw_detail.get("status_date", ""),
            "eta": raw_detail.get("eta", ""),
            "scans": raw_detail.get("scans", []),
            "timeline": raw_detail.get("timeline", []),
            "courier": raw_detail.get("courier", ""),
            "awb": raw_detail.get("awb", ""),
            "tracking_id": raw_detail.get("tracking_id", ""),
            "tracking_url": raw_detail.get("tracking_url", ""),
            "seller": raw_detail.get("seller", ""),
            "address": raw_addr,
            "can_change_address": raw_detail.get("can_change_address", False),
            "can_cancel": raw_detail.get("can_cancel", False)
        }

        return {
            "ok": True,
            "phone": data.get("phone", ""),
            "detail": clean_detail
        }
    except Exception as e:
        print("[!] Get order detail error:", e)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.get("/", response_class=HTMLResponse)
def serve_home():
    html_path = os.path.join(BASE_DIR, "price_checker_index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Price Checker UI Not Found</h1>"
