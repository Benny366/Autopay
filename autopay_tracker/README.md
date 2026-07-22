# 💳 Smart AutoPay Subscription & Payment Tracker

A hackathon-ready web application to track all AutoPay subscriptions across OTT platforms, UPI apps, and more — with reminders, analytics, and full CRUD.

---

## 📁 Folder Structure

```
autopay_tracker/
├── app.py                  ← Flask backend (REST API + fraud logic)
├── subscriptions.json      ← Auto-created JSON database (mock data seeded)
├── requirements.txt        ← Python dependencies
├── README.md               ← This file
└── templates/
    └── index.html          ← Full frontend (Dashboard + Add + Tracker)
```

---

## 🚀 How to Run

### Step 1 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### Step 2 — Start the server
```bash
python app.py
```
✅ Running at: **http://127.0.0.1:5000**

### Step 3 — Open browser
Visit **http://127.0.0.1:5000** — mock data is auto-seeded on first run.

> 💡 **Works offline too!** If Flask is not running, the frontend uses localStorage as a fallback — all features still work in the browser.

---

## 🔌 REST API Endpoints

| Method | Endpoint                     | Description                          |
|--------|------------------------------|--------------------------------------|
| GET    | `/api/subscriptions`         | Get all subscriptions (with filters) |
| POST   | `/api/subscriptions`         | Add a new subscription               |
| PUT    | `/api/subscriptions/<id>`    | Update a subscription                |
| DELETE | `/api/subscriptions/<id>`    | Delete a subscription                |
| GET    | `/api/dashboard`             | Summary stats + reminders            |
| GET    | `/api/history/<id>`          | Mock payment history for a sub       |

### Query Filters (GET /api/subscriptions)
```
?platform=Netflix
?app=PhonePe
?platform=Spotify&app=PhonePe
```

---

## ⚙️ Core Logic Explained

### Status Detection (auto-computed)
```python
today = date.today()
next_payment = date from subscription

if next_payment < today       → OVERDUE  (red)
if next_payment - today ≤ 2  → UPCOMING (yellow)
else                          → ACTIVE   (green)
```

### Reminder System
- Dashboard scans all subscriptions on load
- Any subscription with `next_payment` within 0–2 days shows a **pulsing reminder banner**
- No external API needed — logic runs every page load

### Progress Tracking
```python
months_completed = (today.year - start.year)*12 + (today.month - start.month)
months_remaining = duration - months_completed
progress_percent = months_completed / duration * 100
```

### Monthly Spend Calculation
```python
# Monthly subscriptions → add amount directly
# Yearly subscriptions  → divide amount by 12
monthly_total = sum(
    amount if sub_type == "Monthly" else amount/12
    for each subscription
)
yearly_estimate = monthly_total * 12
```

---

## 🎨 UI Features

| Feature | Details |
|---|---|
| **Dashboard** | Stats (active, upcoming, overdue, monthly spend), reminders, subscription cards, pie chart |
| **Add Subscription** | Full form with all fields, AutoPay toggle |
| **Tracker Table** | Filterable by platform/app/status, progress bars, payment history |
| **Dark/Light Mode** | Toggle in sidebar footer |
| **Pie Chart** | Canvas-based (no external library), shows spend per platform |
| **Toast Alerts** | Success/error notifications on add/edit/delete |
| **Payment History Modal** | Mock history showing all past months |
| **Offline Mode** | Falls back to localStorage if backend is offline |

---

## 🌱 Future Scope
- UPI/bank API integration for real auto-detection
- Push notifications (email/SMS alerts)
- Multi-user authentication
- Budget limits and overspend warnings
- Export to PDF/Excel
