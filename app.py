"""
app.py — Flask API Backend
Chạy: python app.py  hoặc  gunicorn app:app
"""
import os, secrets, functools, threading
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import db

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

# ── AUTH DECORATOR ─────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return jsonify({"ok": False, "msg": "Chưa đăng nhập"}), 401
        return f(*args, **kwargs)
    return decorated

# ── SERVE FRONTEND ─────────────────────────────
@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# ── AUTH ROUTES ────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    d = request.json or {}
    ok, msg = db.create_user(
        d.get("username",""),
        d.get("password",""),
        d.get("name","")
    )
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.json or {}
    ok, msg = db.verify_user(d.get("username",""), d.get("password",""))
    if ok:
        u = d["username"].lower()
        session["username"] = u
        user = db.get_user(u)
        return jsonify({
            "ok": True,
            "user": {
                "username": u,
                "name": user["name"],
                "key_expire": user.get("key_expire"),
                "key_plan": user.get("key_plan"),
                "key_active": db.user_key_active(u),
                "remain_days": db.get_key_remain_days(u),
            }
        })
    return jsonify({"ok": False, "msg": msg})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
@login_required
def me():
    u = session["username"]
    user = db.get_user(u)
    if not user:
        session.clear()
        return jsonify({"ok": False, "msg": "User not found"}), 401
    return jsonify({
        "ok": True,
        "user": {
            "username": u,
            "name": user["name"],
            "key_expire": user.get("key_expire"),
            "key_plan": user.get("key_plan"),
            "key_active": db.user_key_active(u),
            "remain_days": db.get_key_remain_days(u),
            "history": user.get("history", [])[:20]
        }
    })

# ── KEY ROUTES ─────────────────────────────────
@app.route("/api/key/activate", methods=["POST"])
@login_required
def key_activate():
    d = request.json or {}
    key_str = d.get("key","").strip().upper()
    if not key_str:
        return jsonify({"ok": False, "msg": "Vui lòng nhập key"})
    ok, msg = db.activate_key_for_user(key_str, session["username"])
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/key/info", methods=["GET"])
@login_required
def key_info():
    u = session["username"]
    return jsonify({
        "ok": True,
        "active": db.user_key_active(u),
        "remain_days": db.get_key_remain_days(u)
    })

# ── PAYMENT ROUTES ─────────────────────────────
@app.route("/api/payment/create", methods=["POST"])
@login_required
def payment_create():
    d = request.json or {}
    plan_id = d.get("plan_id","")
    if plan_id not in db.PLANS:
        return jsonify({"ok": False, "msg": "Gói không hợp lệ"})
    import string as _s, secrets as _sec
    txn = ''.join(_sec.choice(_s.ascii_uppercase + _s.digits) for _ in range(10))
    pay = db.create_payment(session["username"], plan_id, txn)

    # Notify admin via Telegram (non-blocking)
    def notify():
        try:
            _notify_admin_payment(pay)
        except Exception:
            pass
    threading.Thread(target=notify, daemon=True).start()

    plan = db.PLANS[plan_id]
    return jsonify({
        "ok": True,
        "txn_code": txn,
        "amount": plan["price"],
        "plan_label": plan["label"],
        "bank": os.getenv("BANK_NAME","MBBANK"),
        "account": os.getenv("BANK_ACCOUNT","02444128888"),
        "owner": os.getenv("BANK_OWNER","LE CONG HOAN"),
        "qr_url": f"https://img.vietqr.io/image/MB-{os.getenv('BANK_ACCOUNT','02444128888')}-print.png?amount={plan['price']}&addInfo={txn}%20VIPGAME&accountName={os.getenv('BANK_OWNER','LE CONG HOAN').replace(' ','%20')}"
    })

def _notify_admin_payment(pay: dict):
    token = os.getenv("BOT_TOKEN","")
    admin_ids = [x.strip() for x in os.getenv("ADMIN_IDS","").split(",") if x.strip()]
    if not token or not admin_ids:
        return
    import requests as req
    msg = (
        f"💰 *THANH TOÁN MỚI*\n\n"
        f"👤 User: `{pay['username']}`\n"
        f"📦 Gói: {pay['plan_label']}\n"
        f"💵 Số tiền: {pay['amount']:,}đ\n"
        f"🔑 Mã CK: `{pay['txn_code']}`\n\n"
        f"✅ Xác nhận: `/confirm {pay['txn_code']}`\n"
        f"❌ Từ chối: `/reject {pay['txn_code']}`"
    )
    for aid in admin_ids:
        try:
            req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": aid, "text": msg, "parse_mode": "Markdown"},
                timeout=5
            )
        except Exception:
            pass

@app.route("/api/payment/pending")
@login_required
def payment_pending():
    u = session["username"]
    # Only return user's own pending
    all_pending = db.list_pending_payments()
    mine = [p for p in all_pending if p["username"] == u]
    return jsonify({"ok": True, "payments": mine})

# ── PLANS ROUTE ────────────────────────────────
@app.route("/api/plans")
def plans():
    return jsonify({"ok": True, "plans": db.PLANS})

# ── STATS (public minimal) ─────────────────────
@app.route("/api/stats")
def stats():
    s = db.get_stats()
    return jsonify({"ok": True, "stats": {
        "total_users": s["total_users"],
        "active_users": s["active_users"]
    }})

# ── HEALTH CHECK ───────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "VIP GAME API"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 VIP GAME Server starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
