"""
Smart AutoPay Subscription & Payment Tracker
Backend: Flask + JSON DB + Email (SMTP) + SMS (Twilio) + Daily Scheduler

Install:
    pip install flask flask-cors twilio apscheduler

Run:
    python app.py
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib, json, os, uuid, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# CONFIGURATION  —  set via .env or edit here
# ══════════════════════════════════════════════
CONFIG = {
    "EMAIL_ENABLED":     True,
    "SMTP_HOST":         "smtp.gmail.com",
    "SMTP_PORT":         587,
    "SMTP_USER":         os.getenv("SMTP_USER",  "your_gmail@gmail.com"),
    "SMTP_PASS":         os.getenv("SMTP_PASS",  "your_app_password"),
    "FROM_NAME":         "AutoPay Tracker",
    "SMS_ENABLED":       False,
    "TWILIO_SID":        os.getenv("TWILIO_SID",   "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
    "TWILIO_TOKEN":      os.getenv("TWILIO_TOKEN",  "your_auth_token"),
    "TWILIO_FROM":       os.getenv("TWILIO_FROM",   "+1XXXXXXXXXX"),
}

# ══════════════════════════════════════════════
# JSON  DATABASE  HELPERS
# ══════════════════════════════════════════════
DB_FILE    = "subscriptions.json"
USERS_FILE = "users.json"
ALERT_FILE = "alerts_sent.json"

def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else []
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_db():
    data = load_json(DB_FILE)
    if not data:
        data = _seed()
        save_json(DB_FILE, data)
    return data

def _seed():
    t = datetime.today()
    d = lambda n: (t + timedelta(days=n)).strftime("%Y-%m-%d")
    return [
        {"id": str(uuid.uuid4()), "platform": "Netflix",      "payment_app": "Credit Card", "sub_type": "Monthly", "amount": 649,  "start_date": "2025-01-01", "next_payment": d(2),   "autopay": True,  "duration": 12, "category": "Entertainment", "status": "active", "created_at": t.isoformat()},
        {"id": str(uuid.uuid4()), "platform": "Spotify",      "payment_app": "PhonePe",     "sub_type": "Monthly", "amount": 119,  "start_date": "2025-02-01", "next_payment": d(8),   "autopay": True,  "duration": 12, "category": "Music",         "status": "active", "created_at": t.isoformat()},
        {"id": str(uuid.uuid4()), "platform": "Amazon Prime", "payment_app": "Google Pay",  "sub_type": "Yearly",  "amount": 1499, "start_date": "2025-01-15", "next_payment": d(30),  "autopay": True,  "duration": 12, "category": "Entertainment", "status": "active", "created_at": t.isoformat()},
        {"id": str(uuid.uuid4()), "platform": "Hotstar",      "payment_app": "Paytm",       "sub_type": "Monthly", "amount": 299,  "start_date": "2025-03-01", "next_payment": d(-3),  "autopay": False, "duration": 6,  "category": "Entertainment", "status": "overdue","created_at": t.isoformat()},
        {"id": str(uuid.uuid4()), "platform": "iCloud",       "payment_app": "Credit Card", "sub_type": "Monthly", "amount": 75,   "start_date": "2024-06-01", "next_payment": d(15),  "autopay": True,  "duration": 24, "category": "Cloud Storage", "status": "active", "created_at": t.isoformat()},
        {"id": str(uuid.uuid4()), "platform": "Gym App",      "payment_app": "PhonePe",     "sub_type": "Monthly", "amount": 999,  "start_date": "2024-10-01", "next_payment": d(-10), "autopay": True,  "duration": 6,  "category": "Health",        "status": "expired","created_at": t.isoformat()},
    ]

def compute_status(sub):
    today = datetime.today().date()
    try:
        nxt = datetime.strptime(sub["next_payment"], "%Y-%m-%d").date()
    except Exception:
        return sub.get("status", "active")
    if nxt < today: return "overdue"
    if (nxt - today).days <= 2: return "upcoming"
    return "active"

def months_completed(sub):
    try:
        start = datetime.strptime(sub["start_date"], "%Y-%m-%d").date()
        today = datetime.today().date()
        delta = (today.year - start.year)*12 + (today.month - start.month)
        return max(0, min(delta, sub.get("duration", 12)))
    except Exception:
        return 0

# ══════════════════════════════════════════════
# EMAIL  (Gmail SMTP)
# ══════════════════════════════════════════════
def build_html_email(reminders):
    rows = ""
    for r in reminders:
        due = "TODAY ⚠️" if r["days_left"] == 0 else f"in {r['days_left']} day(s)"
        rows += f"""
        <tr>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0">
            <strong style="color:#1e293b">{r['platform']}</strong><br>
            <span style="font-size:12px;color:#64748b">{r['payment_app']}</span>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;text-align:center">
            <span style="background:#fef3c7;color:#92400e;padding:3px 10px;
                  border-radius:99px;font-size:12px;font-weight:600">Due {due}</span>
          </td>
          <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;
                text-align:right;font-weight:700;color:#0f172a">
            &#8377;{r['amount']:,}
          </td>
        </tr>"""
    total = sum(r["amount"] for r in reminders)
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f8fafc;
      font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:560px;margin:40px auto;background:#fff;
        border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
    <div style="background:linear-gradient(135deg,#4f8ef7,#7c5cfc);
          padding:32px;text-align:center">
      <div style="font-size:40px;margin-bottom:8px">&#128179;</div>
      <h1 style="color:#fff;margin:0;font-size:22px">AutoPay Payment Reminder</h1>
      <p style="color:rgba(255,255,255,.85);margin:6px 0 0;font-size:13px">
        {len(reminders)} subscription(s) due soon</p>
    </div>
    <div style="padding:28px 32px">
      <p style="color:#334155;margin:0 0 20px;font-size:14px;line-height:1.6">
        Hi! The following AutoPay subscriptions will be deducted from your account soon.
        Make sure you have sufficient balance.</p>
      <table width="100%" style="border-collapse:collapse;
            border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">
        <thead>
          <tr style="background:#f1f5f9">
            <th style="padding:10px 16px;text-align:left;font-size:11px;
                  color:#64748b;letter-spacing:1px;text-transform:uppercase">Platform</th>
            <th style="padding:10px 16px;text-align:center;font-size:11px;
                  color:#64748b;letter-spacing:1px;text-transform:uppercase">Due</th>
            <th style="padding:10px 16px;text-align:right;font-size:11px;
                  color:#64748b;letter-spacing:1px;text-transform:uppercase">Amount</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
            padding:16px 20px;margin-top:16px;
            display:flex;justify-content:space-between;align-items:center">
        <span style="color:#64748b;font-size:13px">Total upcoming deductions</span>
        <span style="font-size:22px;font-weight:800;color:#4f8ef7">
          &#8377;{total:,}</span>
      </div>
      <p style="color:#94a3b8;font-size:12px;margin-top:20px;line-height:1.6">
        &#128161; Tip: Cancel unused subscriptions to save money.<br>
        Manage: <a href="http://127.0.0.1:5000" style="color:#4f8ef7">
        AutoPay Tracker Dashboard</a>
      </p>
    </div>
    <div style="background:#f8fafc;padding:14px 32px;text-align:center;
          border-top:1px solid #e2e8f0">
      <p style="color:#94a3b8;font-size:11px;margin:0">
        AutoPay Tracker &bull; Smart Subscription Manager</p>
    </div>
  </div>
</body></html>"""

def send_email(to_email, reminders):
    if not CONFIG["EMAIL_ENABLED"] or not to_email:
        return False, "Email disabled or no recipient set"
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = f"💳 AutoPay Reminder: {len(reminders)} payment(s) due soon"
        msg["From"]    = f"{CONFIG['FROM_NAME']} <{CONFIG['SMTP_USER']}>"
        msg["To"]      = to_email

        plain = "AutoPay Reminder\n\n"
        for r in reminders:
            plain += f"• {r['platform']} — ₹{r['amount']} due in {r['days_left']} day(s) via {r['payment_app']}\n"
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(build_html_email(reminders), "html"))

        with smtplib.SMTP(CONFIG["SMTP_HOST"], CONFIG["SMTP_PORT"]) as s:
            s.starttls()
            s.login(CONFIG["SMTP_USER"], CONFIG["SMTP_PASS"])
            s.send_message(msg)
        log.info(f"✅ Email sent → {to_email}")
        return True, "Email sent successfully"
    except Exception as e:
        log.error(f"❌ Email error: {e}")
        return False, str(e)

# ══════════════════════════════════════════════
# SMS  (Twilio)
# ══════════════════════════════════════════════
def send_sms(to_phone, reminders):
    if not CONFIG["SMS_ENABLED"] or not TWILIO_AVAILABLE or not to_phone:
        return False, "SMS disabled or Twilio not configured"
    try:
        client = TwilioClient(CONFIG["TWILIO_SID"], CONFIG["TWILIO_TOKEN"])
        lines  = ["💳 AutoPay Reminder:"]
        for r in reminders:
            due = "TODAY" if r["days_left"] == 0 else f"in {r['days_left']} day(s)"
            lines.append(f"• {r['platform']}: ₹{r['amount']} due {due} ({r['payment_app']})")
        lines.append(f"\nTotal: ₹{sum(r['amount'] for r in reminders):,}")
        lines.append("Manage: http://127.0.0.1:5000")
        m = client.messages.create(body="\n".join(lines),
                                   from_=CONFIG["TWILIO_FROM"], to=to_phone)
        log.info(f"✅ SMS sent → {to_phone}  SID:{m.sid}")
        return True, f"SMS sent (SID: {m.sid})"
    except Exception as e:
        log.error(f"❌ SMS error: {e}")
        return False, str(e)

# ══════════════════════════════════════════════
# DAILY  SCHEDULED  JOB
# ══════════════════════════════════════════════
def run_daily_alerts():
    log.info("🔔 Running daily alert check...")
    subs      = load_db()
    users     = load_json(USERS_FILE, {"email": "", "phone": ""})
    alert_log = load_json(ALERT_FILE, {})
    today     = datetime.today().date()
    reminders = []

    for s in subs:
        try:
            nxt  = datetime.strptime(s["next_payment"], "%Y-%m-%d").date()
            diff = (nxt - today).days
            if 0 <= diff <= 2:
                key = f"{s['id']}_{today.isoformat()}"
                if key not in alert_log:
                    reminders.append({"platform": s["platform"], "amount": s["amount"],
                                      "days_left": diff, "payment_app": s["payment_app"]})
                    alert_log[key] = datetime.now().isoformat()
        except Exception:
            pass

    if not reminders:
        log.info("No reminders due today.")
        return

    save_json(ALERT_FILE, alert_log)
    if users.get("email"): send_email(users["email"], reminders)
    if users.get("phone"):  send_sms(users["phone"], reminders)

# ══════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════
@app.route("/")
def home(): return render_template("index.html")

@app.route("/api/subscriptions", methods=["GET"])
def get_subs():
    subs = load_db()
    for s in subs:
        s["status"]           = compute_status(s)
        s["months_completed"] = months_completed(s)
        s["months_remaining"] = max(0, s.get("duration",12) - s["months_completed"])
    p = request.args.get("platform"); a = request.args.get("app")
    if p: subs = [s for s in subs if p.lower() in s["platform"].lower()]
    if a: subs = [s for s in subs if a.lower() in s["payment_app"].lower()]
    order = {"overdue":0,"upcoming":1,"active":2,"expired":3}
    subs.sort(key=lambda s: order.get(s["status"],4))
    return jsonify(subs)

@app.route("/api/subscriptions", methods=["POST"])
def add_sub():
    d = request.get_json()
    d["id"] = str(uuid.uuid4()); d["created_at"] = datetime.now().isoformat(); d["status"]="active"
    subs = load_db(); subs.append(d); save_json(DB_FILE, subs)
    return jsonify({"success":True,"id":d["id"]}), 201

@app.route("/api/subscriptions/<sid>", methods=["PUT"])
def update_sub(sid):
    d = request.get_json(); subs = load_db()
    for i,s in enumerate(subs):
        if s["id"]==sid: subs[i]={**s,**d,"id":sid}; save_json(DB_FILE,subs); return jsonify({"success":True})
    return jsonify({"error":"Not found"}),404

@app.route("/api/subscriptions/<sid>", methods=["DELETE"])
def del_sub(sid):
    save_json(DB_FILE,[s for s in load_db() if s["id"]!=sid]); return jsonify({"success":True})

@app.route("/api/dashboard")
def dashboard():
    subs=load_db(); today=datetime.today().date()
    active=upcoming=overdue=expired=0; monthly=0; by_p={}; reminders=[]
    for s in subs:
        st=compute_status(s); s["status"]=st
        if   st=="expired":  expired+=1
        elif st=="overdue":  overdue+=1
        elif st=="upcoming": upcoming+=1
        else:                active+=1
        amt=float(s.get("amount",0))
        m=amt/12 if s.get("sub_type")=="Yearly" else amt
        monthly+=m; by_p[s["platform"]]=by_p.get(s["platform"],0)+m
        try:
            nxt=datetime.strptime(s["next_payment"],"%Y-%m-%d").date(); diff=(nxt-today).days
            if 0<=diff<=2: reminders.append({"platform":s["platform"],"amount":s["amount"],"days_left":diff,"payment_app":s["payment_app"]})
        except Exception: pass
    return jsonify({"total_active":active+upcoming,"upcoming_count":upcoming,"total_overdue":overdue,
                    "total_expired":expired,"monthly_spend":round(monthly,2),"yearly_spend":round(monthly*12,2),
                    "reminders":reminders,"by_platform":by_p})

@app.route("/api/history/<sid>")
def history(sid):
    sub=next((s for s in load_db() if s["id"]==sid),None)
    if not sub: return jsonify([])
    start=datetime.strptime(sub["start_date"],"%Y-%m-%d")
    h=[{"month":(start+timedelta(days=30*i)).strftime("%b %Y"),"amount":sub["amount"],"status":"paid","app":sub["payment_app"]} for i in range(months_completed(sub))]
    return jsonify(list(reversed(h)))

@app.route("/api/settings", methods=["GET"])
def get_settings():
    u=load_json(USERS_FILE,{"email":"","phone":""})
    return jsonify({
        "email": u.get("email",""), "phone": u.get("phone",""),
        "email_enabled":  CONFIG["EMAIL_ENABLED"],
        "sms_enabled":    CONFIG["SMS_ENABLED"],
        "smtp_configured": "your_gmail" not in CONFIG["SMTP_USER"],
        "twilio_configured": "ACxx" not in CONFIG["TWILIO_SID"],
    })

@app.route("/api/settings", methods=["POST"])
def save_settings():
    d=request.get_json(); u=load_json(USERS_FILE,{"email":"","phone":""})
    for k in ("email","phone"): u[k]=d.get(k,u.get(k,""))
    save_json(USERS_FILE,u)
    for k,c in [("smtp_user","SMTP_USER"),("smtp_pass","SMTP_PASS"),
                ("twilio_sid","TWILIO_SID"),("twilio_token","TWILIO_TOKEN"),("twilio_from","TWILIO_FROM")]:
        if d.get(k): CONFIG[c]=d[k]
    if "email_enabled" in d: CONFIG["EMAIL_ENABLED"]=bool(d["email_enabled"])
    if "sms_enabled"   in d: CONFIG["SMS_ENABLED"]  =bool(d["sms_enabled"])
    return jsonify({"success":True})

@app.route("/api/alerts/test", methods=["POST"])
def test_alert():
    d=request.get_json(); u=load_json(USERS_FILE,{"email":"","phone":""})
    to_email=d.get("email") or u.get("email")
    to_phone=d.get("phone") or u.get("phone")
    channel =d.get("channel","both")
    subs=load_db(); today=datetime.today().date(); reminders=[]
    for s in subs:
        try:
            nxt=datetime.strptime(s["next_payment"],"%Y-%m-%d").date(); diff=(nxt-today).days
            if 0<=diff<=2: reminders.append({"platform":s["platform"],"amount":s["amount"],"days_left":diff,"payment_app":s["payment_app"]})
        except Exception: pass
    if not reminders:
        reminders=[{"platform":"Netflix (Test)","amount":649,"days_left":2,"payment_app":"Credit Card"}]
    results={}
    if channel in ("email","both") and to_email:
        ok,msg=send_email(to_email,reminders); results["email"]={"sent":ok,"message":msg,"to":to_email}
    if channel in ("sms","both") and to_phone:
        ok,msg=send_sms(to_phone,reminders);   results["sms"]  ={"sent":ok,"message":msg,"to":to_phone}
    if not results: return jsonify({"success":False,"message":"No email/phone configured"}),400
    return jsonify({"success":True,"results":results,"reminders_count":len(reminders)})

@app.route("/api/alerts/log")
def alert_log():
    data=load_json(ALERT_FILE,{})
    entries=sorted([{"key":k,"sent_at":v} for k,v in data.items()],key=lambda x:x["sent_at"],reverse=True)
    return jsonify(entries[:50])

# ══════════════════════════════════════════════
# START
# ══════════════════════════════════════════════
scheduler = BackgroundScheduler()
scheduler.add_job(run_daily_alerts,"cron",hour=9,minute=0,id="daily_alert",replace_existing=True)

if __name__=="__main__":
    scheduler.start()
    log.info("⏰ Scheduler active — alerts fire daily at 09:00 AM")
    log.info("✅ Server → http://127.0.0.1:5000")
    try:
        app.run(debug=False, use_reloader=False)
    finally:
        scheduler.shutdown()
