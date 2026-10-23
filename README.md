# 🛒 Premium Digital Voucher & Coupon Telegram Bot

An asynchronous, high-performance Telegram store bot built with **aiogram 3**, **MongoDB Atlas (Motor)**, and **FastAPI**. Designed for 24/7 reliability, high transaction throughput, automated inventory management, and zero latency.

---

## ✨ Features & Architecture

### 🛍️ Client Experience
* **Interactive Shopping Flow**: Multi-category voucher browsing, real-time stock verification, quantity selector, and instant order creation.
* **Instant Checkout & UPI Integration**: One-click **"Pay via UPI App"** deep links for PhonePe, Google Pay, and Paytm, with category-specific or store-wide QR codes.
* **Screen Recording Security & Proof**: Visual verification steps requiring uncut screen recording proof for guaranteed buyer & seller protection.
* **Voucher Recovery & History**: Comprehensive order history receipt view, copyable coupon codes with auto-split PIN detection, and isolated order lookup.
* **Referral & Loyalty Program**: Visual progress bars, referral invite links, automated referral tracking, redeemable rewards, and leaderboards.
* **24/7 Human Support & FAQs**: Live contact list for support channels and agents.

### 🔐 Admin & Merchant Control Panel
* **Live Orders Dashboard**: Status breakdowns (Pending, Completed, Errors, Timeouts) and activity counters.
* **Rapid Bulk Stock Upload**: Blazing fast atomic bulk code ingestion via `.txt` upload or comma/newline separation.
* **Flash Sales Engine**: Timed promotional pricing with automatic price reversion and background alerts.
* **Global Notifications**: Multi-admin order alerts with inline 1-click Approve / Reject buttons.
* **Broadcast Engine**: Rate-limit-aware broadcast system with automatic flood-wait handling (`TelegramRetryAfter`) supporting text, photos, videos, and documents.
* **Security & Anti-Abuse**: Duplicate UTR prevention, strike tracking, automated suspicious activity mitigation, and blacklisting.

---

## 🛠️ Tech Stack & Requirements

* **Python 3.11+ / 3.14**
* **aiogram 3.20+** (Async Telegram Bot framework)
* **motor & pymongo** (Async MongoDB Driver)
* **fastapi & uvicorn** (Keep-alive webserver for cloud environments like Render / Railway / Heroku)
* **python-dotenv** (Environment configuration)
* **certifi** (SSL CA bundle)

---

## 🚀 Running the Bot

### Local / VPS Execution
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run system verification test
python verify_system.py

# 3. Start the bot
python bot.py
```

### Docker Deployment
```bash
# Build the optimized multi-stage image
docker build -t shein-coupon-bot .

# Run container
docker run -d --name coupon-bot --env-file .env shein-coupon-bot
```

---

## 🧪 System Verification

Run the built-in end-to-end verification suite:
```bash
python verify_system.py
```
This tests:
1. MongoDB connectivity & ping
2. Atomic ID counter blocks
3. Category creation & bulk coupon ingestion
4. Transaction reservation & anti-duplicate UTR checks
5. User transaction search isolation
6. Telegram HTML formatting & sanitization

---

## 🛡️ License
Private proprietary commercial bot. All rights reserved.
