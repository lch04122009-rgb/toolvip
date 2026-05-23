"""db.py — Database manager (JSON files in /data/)"""
import json, os, time, hashlib, secrets, string
from pathlib import Path

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)

F_USERS    = DATA / "users.json"
F_KEYS     = DATA / "keys.json"
F_PAYMENTS = DATA / "payments.json"
F_LOGS     = DATA / "logs.json"

PLANS = {
    "1d": {"label":"KEY 1 NGÀY",   "days":1,  "price":35000},
    "3d": {"label":"KEY 3 NGÀY",   "days":3,  "price":60000},
    "7d": {"label":"KEY 7 NGÀY",   "days":7,  "price":95000},
    "1m": {"label":"KEY 1 THÁNG",  "days":30, "price":175000},
    "2m": {"label":"KEY 2 THÁNG",  "days":60, "price":220000},
    "3m": {"label":"KEY 3 THÁNG",  "days":90, "price":270000},
}

def _load(f):
    try:
        if Path(f).exists():
            return json.loads(Path(f).read_text("utf-8"))
    except: pass
    return {}

def _save(f, d):
    Path(f).write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")

def _now(): return int(time.time())
def _ts(ts): 
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
def _hash(p): return hashlib.sha256(p.encode()).hexdigest()
def _genkey(plan):
    c = string.ascii_uppercase + string.digits
    return f"VIP-{plan.upper()}-{''.join(secrets.choice(c) for _ in range(8))}"

def _log(action, user, detail):
    d = _load(F_LOGS)
    d.setdefault("logs", []).insert(0, {"action":action,"user":user,"detail":detail,"time":_ts(_now()),"ts":_now()})
    d["logs"] = d["logs"][:500]
    _save(F_LOGS, d)

# ── USERS ──────────────────────────────────────
def get_users(): return _load(F_USERS)
def get_user(u): return get_users().get(u.lower())

def create_user(username, password, name):
    u = username.lower().strip()
    if len(u) < 4: return False, "Tên đăng nhập tối thiểu 4 ký tự"
    if len(password) < 6: return False, "Mật khẩu tối thiểu 6 ký tự"
    users = get_users()
    if u in users: return False, "Tên đăng nhập đã tồn tại"
    users[u] = {"username":u,"name":name.strip(),"password":_hash(password),
                "created_at":_now(),"key_expire":None,"key_plan":None,
                "used_key":None,"history":[]}
    _save(F_USERS, users)
    _log("register", u, f"Đăng ký: {name}")
    return True, "OK"

def verify_user(username, password):
    usr = get_user(username)
    if not usr: return False, "Tài khoản không tồn tại"
    if usr["password"] != _hash(password): return False, "Mật khẩu không đúng"
    return True, "OK"

def update_user(u, data):
    users = get_users()
    if u.lower() in users:
        users[u.lower()].update(data)
        _save(F_USERS, users)

def add_history(u, action):
    users = get_users()
    k = u.lower()
    if k in users:
        h = users[k].get("history", [])
        h.insert(0, {"action":action,"time":_ts(_now()),"ts":_now()})
        users[k]["history"] = h[:50]
        _save(F_USERS, users)

def key_active(u):
    usr = get_user(u)
    if not usr: return False
    exp = usr.get("key_expire")
    return bool(exp and exp > _now())

def remain_days(u):
    usr = get_user(u)
    if not usr: return 0
    exp = usr.get("key_expire")
    if not exp or exp <= _now(): return 0
    return max(0, int((exp - _now()) / 86400))

# ── KEYS ───────────────────────────────────────
def get_keys(): return _load(F_KEYS)

def create_key(plan_id, by="admin", note=""):
    if plan_id not in PLANS: return False, f"Gói không hợp lệ: {plan_id}"
    keys = get_keys()
    k = _genkey(plan_id)
    while k in keys: k = _genkey(plan_id)
    plan = PLANS[plan_id]
    keys[k] = {"key":k,"plan_id":plan_id,"plan_label":plan["label"],
               "days":plan["days"],"price":plan["price"],
               "created_at":_now(),"created_by":by,
               "used_by":None,"used_at":None,"expire_at":None,
               "note":note,"status":"active"}
    _save(F_KEYS, keys)
    _log("create_key", by, f"Tạo {k} gói {plan['label']}")
    return True, k

def create_keys_batch(plan_id, count, by="admin"):
    result = []
    for _ in range(min(count, 50)):
        ok, k = create_key(plan_id, by)
        if ok: result.append(k)
    return True, result

def activate_key(key_str, username):
    keys = get_keys()
    users = get_users()
    u = username.lower()
    if key_str not in keys: return False, "❌ Key không hợp lệ"
    kd = keys[key_str]
    if kd["status"] == "used":
        if kd["used_by"] == u: return False, "⚠️ Key này đang dùng trên tài khoản bạn"
        return False, "❌ Key đã được dùng bởi tài khoản khác"
    if kd["status"] == "expired": return False, "❌ Key đã hết hạn"
    if u not in users: return False, "Tài khoản không tồn tại"
    cur_exp = users[u].get("key_expire") or 0
    base = cur_exp if cur_exp > _now() else _now()
    new_exp = base + kd["days"] * 86400
    keys[key_str].update({"used_by":u,"used_at":_now(),"expire_at":new_exp,"status":"used"})
    _save(F_KEYS, keys)
    users[u].update({"key_expire":new_exp,"key_plan":kd["plan_label"],"used_key":key_str})
    _save(F_USERS, users)
    add_history(u, f"Kích hoạt {kd['plan_label']} · ...{key_str[-6:]}")
    _log("activate_key", u, f"Key {key_str} → {kd['plan_label']}")
    return True, f"✅ Thành công! {kd['plan_label']} — {kd['days']} ngày"

def delete_key(key_str):
    keys = get_keys()
    if key_str in keys and keys[key_str]["status"] == "active":
        del keys[key_str]; _save(F_KEYS, keys); return True
    return False

def list_active_keys(): return [v for v in get_keys().values() if v["status"]=="active"]
def list_used_keys():   return [v for v in get_keys().values() if v["status"]=="used"]

# ── PAYMENTS ───────────────────────────────────
def get_payments(): return _load(F_PAYMENTS)

def create_payment(username, plan_id, txn_code):
    pays = get_payments()
    plan = PLANS[plan_id]
    pid = f"PAY-{txn_code}"
    pays[pid] = {"id":pid,"username":username,"plan_id":plan_id,
                 "plan_label":plan["label"],"amount":plan["price"],
                 "txn_code":txn_code,"status":"pending",
                 "created_at":_now(),"created_str":_ts(_now()),
                 "confirmed_at":None,"confirmed_by":None,"key_given":None,"note":""}
    _save(F_PAYMENTS, pays)
    _log("pay_create", username, f"{pid} {plan['label']} {plan['price']:,}đ")
    return pays[pid]

def confirm_payment(txn_code, by="admin"):
    pays = get_payments()
    found = next(((pid,p) for pid,p in pays.items()
                  if p["txn_code"]==txn_code and p["status"]=="pending"), None)
    if not found: return False, "Không tìm thấy GD pending với mã này", None
    pid, p = found
    ok, key = create_key(p["plan_id"], f"auto:{by}", f"Auto {txn_code}")
    if not ok: return False, f"Tạo key thất bại: {key}", None
    ok2, msg = activate_key(key, p["username"])
    pays[pid].update({"status":"confirmed","confirmed_at":_now(),"confirmed_by":by,"key_given":key})
    _save(F_PAYMENTS, pays)
    add_history(p["username"], f"Thanh toán xác nhận {p['plan_label']} {p['amount']:,}đ")
    _log("pay_confirm", by, f"{pid} → key {key}")
    return True, key, pays[pid]

def reject_payment(txn_code, reason="", by="admin"):
    pays = get_payments()
    for pid, p in pays.items():
        if p["txn_code"]==txn_code and p["status"]=="pending":
            pays[pid].update({"status":"rejected","confirmed_at":_now(),"confirmed_by":by,"note":reason})
            _save(F_PAYMENTS, pays)
            add_history(p["username"], f"Thanh toán bị từ chối: {p['plan_label']}")
            return True
    return False

def list_pending(): 
    return sorted([p for p in get_payments().values() if p["status"]=="pending"], key=lambda x:x["created_at"])

def get_payment_by_txn(txn):
    return next((p for p in get_payments().values() if p["txn_code"]==txn), None)

def get_stats():
    users = get_users(); keys = get_keys(); pays = get_payments()
    return {
        "total_users": len(users),
        "active_users": sum(1 for u in users.values() if u.get("key_expire") and u["key_expire"]>_now()),
        "total_keys": len(keys),
        "active_keys": sum(1 for k in keys.values() if k["status"]=="active"),
        "used_keys": sum(1 for k in keys.values() if k["status"]=="used"),
        "pending_pays": sum(1 for p in pays.values() if p["status"]=="pending"),
        "confirmed_pays": sum(1 for p in pays.values() if p["status"]=="confirmed"),
        "revenue": sum(p["amount"] for p in pays.values() if p["status"]=="confirmed"),
    }

def get_logs(n=50): return _load(F_LOGS).get("logs",[])[:n]
