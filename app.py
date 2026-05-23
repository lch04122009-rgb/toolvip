"""app.py — Flask API Backend"""
import os, secrets, threading, functools
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import db

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
CORS(app, supports_credentials=True, origins="*")

def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **kw):
        if "username" not in session:
            return jsonify({"ok":False,"msg":"Chưa đăng nhập"}), 401
        return f(*a, **kw)
    return wrap

# ── STATIC ──────────────────────────────────
@app.route("/")
def index(): return send_from_directory("templates", "index.html")

@app.route("/static/<path:fn>")
def static_f(fn): return send_from_directory("static", fn)

# ── AUTH ────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    d = request.json or {}
    ok, msg = db.create_user(d.get("username",""), d.get("password",""), d.get("name",""))
    return jsonify({"ok":ok,"msg":msg})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.json or {}
    ok, msg = db.verify_user(d.get("username",""), d.get("password",""))
    if ok:
        u = d["username"].lower()
        session["username"] = u
        usr = db.get_user(u)
        return jsonify({"ok":True,"user":_user_info(u, usr)})
    return jsonify({"ok":False,"msg":msg})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok":True})

@app.route("/api/me")
@login_required
def me():
    u = session["username"]
    usr = db.get_user(u)
    if not usr: session.clear(); return jsonify({"ok":False,"msg":"Not found"}), 401
    info = _user_info(u, usr)
    info["history"] = usr.get("history",[])[:20]
    return jsonify({"ok":True,"user":info})

def _user_info(u, usr):
    return {
        "username": u,
        "name": usr["name"],
        "key_expire": usr.get("key_expire"),
        "key_plan": usr.get("key_plan"),
        "used_key": usr.get("used_key"),
        "key_active": db.key_active(u),
        "remain_days": db.remain_days(u),
    }

# ── KEY ─────────────────────────────────────
@app.route("/api/key/activate", methods=["POST"])
@login_required
def key_activate():
    d = request.json or {}
    k = d.get("key","").strip().upper()
    if not k: return jsonify({"ok":False,"msg":"Vui lòng nhập key"})
    ok, msg = db.activate_key(k, session["username"])
    return jsonify({"ok":ok,"msg":msg})

# ── PAYMENT ─────────────────────────────────
@app.route("/api/plans")
def plans(): return jsonify({"ok":True,"plans":db.PLANS})

@app.route("/api/payment/create", methods=["POST"])
@login_required
def pay_create():
    d = request.json or {}
    plan_id = d.get("plan_id","")
    if plan_id not in db.PLANS:
        return jsonify({"ok":False,"msg":"Gói không hợp lệ"})
    import string as _s
    txn = ''.join(secrets.choice(_s.ascii_uppercase+_s.digits) for _ in range(10))
    pay = db.create_payment(session["username"], plan_id, txn)
    # Notify admin
    threading.Thread(target=_notify_admin, args=(pay,), daemon=True).start()
    plan = db.PLANS[plan_id]
    acct = os.getenv("BANK_ACCOUNT","02444128888")
    owner = os.getenv("BANK_OWNER","LE CONG HOAN")
    qr = f"https://img.vietqr.io/image/MB-{acct}-print.png?amount={plan['price']}&addInfo={txn}%20VIPGAME&accountName={owner.replace(' ','%20')}"
    return jsonify({"ok":True,"txn_code":txn,"amount":plan["price"],
                   "plan_label":plan["label"],"qr_url":qr,
                   "bank":"MBBANK","account":acct,"owner":owner})

@app.route("/api/payment/pending")
@login_required
def pay_pending():
    u = session["username"]
    mine = [p for p in db.list_pending() if p["username"]==u]
    return jsonify({"ok":True,"payments":mine})

# ── CASSO WEBHOOK (thanh toán tự động) ──────
@app.route("/api/webhook/casso", methods=["POST"])
def casso_webhook():
    """
    Casso gửi POST khi có tiền vào TK.
    Tự động match mã CK với đơn pending rồi kích hoạt key.
    """
    secret = request.headers.get("x-api-key","")
    expected = os.getenv("CASSO_WEBHOOK_SECRET","")
    if expected and secret != expected:
        return jsonify({"error":"unauthorized"}), 401

    data = request.json or {}
    records = data.get("data",[]) or [data]  # hỗ trợ cả 2 format Casso

    processed = 0
    for rec in records:
        desc = str(rec.get("description","") or rec.get("memo","") or "").upper()
        amount = int(rec.get("amount",0) or 0)
        # Tìm txn code 10 ký tự trong mô tả
        import re
        codes = re.findall(r'\b[A-Z0-9]{10}\b', desc)
        for code in codes:
            pay = db.get_payment_by_txn(code)
            if pay and pay["status"]=="pending":
                # Kiểm tra số tiền
                if amount >= pay["amount"]:
                    ok, key, pdata = db.confirm_payment(code, "casso_auto")
                    if ok:
                        processed += 1
                        threading.Thread(target=_notify_user_key,
                                       args=(pdata["username"], key, pdata), daemon=True).start()
                        threading.Thread(target=_notify_admin_confirmed,
                                       args=(pdata, key), daemon=True).start()

    return jsonify({"ok":True,"processed":processed})

@app.route("/api/webhook/sepay", methods=["POST"])
def sepay_webhook():
    """SePay webhook format"""
    data = request.json or {}
    desc = str(data.get("content","") or data.get("description","") or "").upper()
    amount = int(data.get("transferAmount",0) or 0)
    import re
    codes = re.findall(r'\b[A-Z0-9]{10}\b', desc)
    for code in codes:
        pay = db.get_payment_by_txn(code)
        if pay and pay["status"]=="pending" and amount >= pay["amount"]:
            ok, key, pdata = db.confirm_payment(code, "sepay_auto")
            if ok:
                threading.Thread(target=_notify_user_key,
                               args=(pdata["username"], key, pdata), daemon=True).start()
                threading.Thread(target=_notify_admin_confirmed,
                               args=(pdata, key), daemon=True).start()
    return jsonify({"ok":True})

# ── NOTIFY HELPERS ──────────────────────────
def _tg_send(chat_id, text):
    import requests
    token = os.getenv("BOT_TOKEN","8547766821:AAHxHXAPqYLYWZHiDMLg78chMQeVkGySN1Y")
    if not token: return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                     json={"chat_id":chat_id,"text":text,"parse_mode":"Markdown"},
                     timeout=5)
    except: pass

def _notify_admin(pay):
    admin_ids = [x.strip() for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()]
    msg = (f"💰 *THANH TOÁN MỚI*\n\n"
           f"👤 User: `{pay['username']}`\n"
           f"📦 Gói: {pay['plan_label']}\n"
           f"💵 Số tiền: {pay['amount']:,}đ\n"
           f"🔑 Mã CK: `{pay['txn_code']}`\n\n"
           f"✅ Tự động kích hoạt khi CK đúng mã\n"
           f"Xác nhận thủ công: `/confirm {pay['txn_code']}`")
    for aid in admin_ids: _tg_send(aid, msg)

def _notify_admin_confirmed(pay, key):
    admin_ids = [x.strip() for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()]
    msg = (f"✅ *ĐÃ XÁC NHẬN TỰ ĐỘNG*\n\n"
           f"👤 User: `{pay['username']}`\n"
           f"📦 Gói: {pay['plan_label']}\n"
           f"💵 {pay['amount']:,}đ\n"
           f"🔑 Key đã cấp: `{key}`")
    for aid in admin_ids: _tg_send(aid, msg)

def _notify_user_key(username, key, pay):
    """Gửi key cho user qua Telegram nếu họ đã link TG"""
    usr = db.get_user(username)
    if not usr: return
    tg_id = usr.get("telegram_id")
    if not tg_id: return
    msg = (f"🎉 *Key đã được kích hoạt!*\n\n"
           f"📦 Gói: {pay['plan_label']}\n"
           f"🔑 Key: `{key}`\n"
           f"📅 Hiệu lực: {pay['plan_label']}\n\n"
           f"Vào website để sử dụng tool dự đoán!")
    _tg_send(tg_id, msg)

@app.route("/health")
def health(): return jsonify({"status":"ok"})

if __name__ == "__main__":
    port = int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=False)
