# 🚀 Meesho Autonomous Hunter & Order Automation Suite

A complete, production-ready automation framework for **Meesho** that features:
- **Autonomous First-Order Discount Hunter** (Targeting Upto ₹110 OFF / ₹170 Bucket / ₹83 UPI)
- **Multi-Provider SMS OTP Integration** (OTPDoctor, PremiumOTP, UOTP)
- **Telegram Bot Automation Engine** (Telethon-powered automation for `@MeeshoOrderBot` and `@ckmeesho_bot`)
- **Customer Price Checker & Order Tracker Web App** (FastAPI backend + interactive Tailwind dashboard)
- **Central VPS Web Controller** for managing active hunter loops, server selection, and live logs

---

## 📑 Table of Contents
1. [System Architecture](#-system-architecture)
2. [Key Features](#-key-features)
3. [File Structure & Core Components](#-file-structure--core-components)
4. [Prerequisites & Requirements](#-prerequisites--requirements)
5. [Quick Start & Installation](#-quick-start--installation)
6. [Environment Configuration (.env)](#-environment-configuration-env)
7. [How to Run Each Script](#-how-to-run-each-script)
   - [1. Autonomous Offer Hunter (`hunter_engine.py`)](#1-autonomous-offer-hunter-hunter_enginepy)
   - [2. CK Meesho Hunter (`ck_hunter_engine.py`)](#2-ck-meesho-hunter-ck_hunter_enginepy)
   - [3. Web Controller Dashboard (`vps_web_server.py`)](#3-web-controller-dashboard-vps_web_serverpy)
   - [4. Customer Price Checker Web App (`price_checker_app.py`)](#4-customer-price-checker-web-app-price_checker_apppy)
   - [5. Order Bot Backend Service (`order_bot_service.py`)](#5-order-bot-backend-service-order_bot_servicepy)
8. [24/7 Deployment via Systemd (VPS / Linux)](#-247-deployment-via-systemd-vps--linux)
9. [The 'Optimal Offer Preservation' Flow Explained](#-the-optimal-offer-preservation-flow-explained)
10. [Security & Privacy Guidelines](#-security--privacy-guidelines)

---

## 🏗 System Architecture

```text
               +-------------------------------------------+
               |           Central Web Controller          |
               |        (vps_web_server.py :8000)          |
               +---------------------+---------------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
+-----------------------------+             +-----------------------------+
|    Autonomous Hunter        |             |  Customer Price Checker     |
|   (hunter_engine.py)        |             | (price_checker_app.py :8080)|
+--------------+--------------+             +--------------+--------------+
               |                                           |
   +-----------+-----------+                               |
   |                       |                               v
   v                       v                 +-----------------------------+
[Telegram Bots]     [SMS Providers]          |   Track Orders & Prices     |
- @MeeshoOrderBot   - OTPDoctor (13 srv)     | (price_checker_index.html)  |
- @ckmeesho_bot     - PremiumOTP (5 srv)     +-----------------------------+
                    - UOTP (India srv)
```

---

## ✨ Key Features

1. **Intelligent Offer Locking & Rerolling**:
   - Automatically navigates bot menus (`Add Account` -> `Login with Number`).
   - Rerolls offers via inline buttons until the target discount is locked (e.g. `Upto ₹120 OFF`, `Bucket: ₹190`, `Final: ₹91`, `UPI: ₹67`).
2. **Offer Preservation on Timeout ('Change Number' Protocol)**:
   - When waiting for an OTP from an SMS provider (with a configurable 3-minute / 180s timeout), if no OTP arrives, the engine automatically clicks `✏️ Change Number`.
   - **Crucial**: It never sends `/start` or resets the session, preserving the high-value locked discount for the next fresh number!
3. **Automated Freshness Pre-check**:
   - Before submitting numbers to the Telegram bot, numbers are checked against Meesho's user database to verify they are fresh (unregistered) to maximize discount success rates.
4. **Export & Session Harvesting**:
   - Automatically downloads and extracts account session JSON files exported by the bot, enriching them with discount tags and syncing them to local/remote storage.
5. **Real-Time Customer Price Checker Dashboard**:
   - Web portal for customers and admins to calculate real-time product prices, apply custom profit margins, and track live order delivery stages.

---

## 📂 File Structure & Core Components

| File | Description |
| :--- | :--- |
| **`hunter_engine.py`** | Main autonomous engine that controls `@MeeshoOrderBot`, locks offers, buys SIMs, handles OTPs, and exports account sessions. |
| **`ck_hunter_engine.py`** | Specialized hunter module tailored for `@ckmeesho_bot` and PremiumOTP servers. |
| **`sms_providers.py`** | Unified API adapter for SMS services (**OTPDoctor**, **PremiumOTP**, and **UOTP**) including balance checking, number buying, OTP polling, and refunding. |
| **`price_checker_app.py`** | FastAPI web server providing price calculation APIs, margin control, order tracking, and account management. |
| **`price_checker_index.html`**| Responsive frontend for the price checker with live search, account list, margin adjustment, and tracking tabs. |
| **`vps_web_server.py`** | Master control server running on port 8000 to start/stop hunters, view logs, probe servers, and display active processes. |
| **`dashboard.html`** | Web dashboard UI for `vps_web_server.py`. |
| **`order_bot_service.py`** | Core service that provides local endpoints for session switching, token verification, and order placement. |
| **`meesho_core_engine.py`** | Internal engine handling Meesho cart manipulation, address validation, and payment token generation. |
| **`meesho_product_engine.py`**| Product search parser and authentic price extraction engine. |
| **`meesho_web_engine.py`** | Browser header and session injector for interacting with Meesho web endpoints. |
| **`auto_fod_account_hunter.py`**| Legacy/standalone First-Order-Discount account harvester. |
| **`sync_missing_accounts.py`** | Utility to sync harvested accounts between local JSON storage and remote Mini Apps. |
| **`.env.example`** | Template file containing all required environment variables and API keys. |
| **`requirements.txt`** | Python dependencies required to run the entire suite. |

---

## 📋 Prerequisites & Requirements

- **Python**: Version 3.10 or higher (Python 3.10, 3.11, 3.12, 3.13, 3.14 supported).
- **Telegram Account**: An active Telegram account with `api_id` and `api_hash` obtained from [my.telegram.org](https://my.telegram.org).
- **SMS Provider Account**: An API key from at least one supported SMS provider:
  - [OTPDoctor](https://otpdoctor.com)
  - [PremiumOTP](https://premiumotp.pro)
  - [UOTP](https://uotp.in)
- **Operating System**: Linux (Ubuntu 20.04/22.04/24.04 recommended for 24/7 VPS hosting) or Windows 10/11 for local development.

---

## ⚡ Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Rajesh248810/automation15.git
cd automation15
```

### 2. Create and Activate a Virtual Environment
**On Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows (PowerShell):**
```powershell
python -m venv venv
.env\Scripts\Activate.ps1
```

### 3. Install Required Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔑 Environment Configuration (.env)

Copy the provided `.env.example` template to create your `.env` file:

```bash
cp .env.example .env
```

Open `.env` in your text editor and fill in your actual credentials:

```env
# Telegram API Credentials (from https://my.telegram.org)
TELEGRAM_API_ID=2040
TELEGRAM_API_HASH=your_actual_telegram_api_hash

# SMS Provider API Keys
OTPDOCTOR_API_KEY=your_otpdoctor_api_key
PREMIUMOTP_API_KEY=your_premiumotp_api_key
UOTP_API_KEY=your_uotp_api_key

# Remote Mini App / Web Backend Integration
WEBAPP_TOKEN=your_webapp_token_here
WEBAPP_BASE_URL=https://pricetrackerpro.fojadomain.fun

# Default Fallback Account
DEFAULT_ACCOUNT_FILE=meesho_account.json
```

> **IMPORTANT**: Never commit your `.env` file or `*.session` files to Git. They are automatically ignored by `.gitignore`.

---

## 🏃 How to Run Each Script

### 1. Autonomous Offer Hunter (`hunter_engine.py`)
This is the primary automated bot that communicates with `@MeeshoOrderBot`, locks the target ₹120 offer, purchases numbers, submits OTPs, and exports account sessions.

```bash
# Run with default settings (1 account, OTPDoctor provider):
python hunter_engine.py

# Run with command-line arguments:
# python hunter_engine.py <target_count> <provider_name> <servers_filter>
python hunter_engine.py 5 otpdoctor "20383,20325,19826"
```

*Arguments:*
- `target_count`: Number of successful accounts to hunt (e.g. `5`).
- `provider_name`: `otpdoctor`, `premiumotp`, or `uotp`.
- `servers_filter`: Comma-separated server IDs or server names to use.

---

### 2. CK Meesho Hunter (`ck_hunter_engine.py`)
Used for hunting on `@ckmeesho_bot` with PremiumOTP:

```bash
# Run with all PremiumOTP servers:
python ck_hunter_engine.py

# Run with specific servers:
python ck_hunter_engine.py premium_in14,premium_in11
```

---

### 3. Web Controller Dashboard (`vps_web_server.py`)
Provides a web-based control panel on port `8000` to start, monitor, and stop hunter routines, inspect balances, and configure server filters.

```bash
uvicorn vps_web_server:app --host 0.0.0.0 --port 8000
```
Open your browser and navigate to: `http://localhost:8000/` (or your VPS IP).

---

### 4. Customer Price Checker Web App (`price_checker_app.py`)
Provides the customer-facing frontend on port `8080` where users can search Meesho catalog items, calculate prices with custom profit margins, and track delivery stages of existing orders.

```bash
uvicorn price_checker_app:app --host 0.0.0.0 --port 8080
```
Open your browser and navigate to: `http://localhost:8080/`.

---

### 5. Order Bot Backend Service (`order_bot_service.py`)
The local backend microservice that bridges order placements and account session switching on port `8090`:

```bash
uvicorn order_bot_service:app --host 0.0.0.0 --port 8090
```

---

## 🌐 24/7 Deployment via Systemd (VPS / Linux)

To run the suite 24/7 continuously on an Ubuntu/Debian VPS, configure systemd unit files:

### 1. Hunter Web Controller Service (`/etc/systemd/system/meesho_hunter_web.service`)
```ini
[Unit]
Description=Meesho Autonomous Hunter Web Controller
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/automation15
ExecStart=/path/to/automation15/venv/bin/uvicorn vps_web_server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 2. Price Checker Web Service (`/etc/systemd/system/meesho_price_checker.service`)
```ini
[Unit]
Description=Meesho Customer Price Checker Web App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/automation15
ExecStart=/path/to/automation15/venv/bin/uvicorn price_checker_app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Enable & Start Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable meesho_hunter_web meesho_price_checker
sudo systemctl start meesho_hunter_web meesho_price_checker
```

---

## 🔄 The 'Optimal Offer Preservation' Flow Explained

Standard scripts usually send `/start` on failure, which causes Meesho bots to re-randomize or degrade the discount offer. This framework implements the **Optimal Flow**:

1. **Offer Locking**: The bot rerolls offers until the desired tier is hit (`Upto ₹120 OFF`, `Bucket: ₹190`, `Final: ₹91`, `UPI: ₹67`).
2. **Fresh Number Acquisition**: A pre-verified fresh number is acquired from the SMS provider.
3. **Phone Submission**: The 10-digit number is sent to the bot.
4. **If Registered**: If the bot reports the number is already used, the script immediately clicks **`✏️ Change Number`**. The high-tier offer remains locked on screen!
5. **3-Minute OTP Timeout**: The script polls the SMS provider for up to 180 seconds.
6. **Automatic Fallback**: If no SMS arrives within 180 seconds:
   - The activation is cancelled and auto-refunded on the SMS provider.
   - The script clicks **`✏️ Change Number`** (never `/start`).
   - The standby fresh number is submitted immediately, keeping the offer active!

---

## 🔒 Security & Privacy Guidelines

- **Never share your `.session` files**: Telegram session files grant full access to your Telegram account. They must remain private on your machine.
- **Never commit `.env`**: Always use `.env.example` when sharing or committing code.
- **Keep API keys secret**: Regularly cycle your SMS provider API keys if you suspect any unauthorized access.

---

## 📄 License
This project is open-source and provided for educational and automation demonstration purposes.
