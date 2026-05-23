"""
db.py — Quản lý dữ liệu: users, keys, payments
Dùng JSON files trong /data/ (dễ deploy, không cần DB riêng)
"""
import json, os, time, hashlib, secrets, string
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE   = DATA_DIR / "users.json"
KEYS_FILE    = DATA_DIR / "keys.json"
PAYMENTS_FILE= DATA_DIR / "payments.json"
LOGS_FILE    = DATA_DIR / "logs.json"

# ── PLANS ──────────────────────────────────────
PLANS = {
    "1d":  {"label": "KEY 1 NGÀY",   "days": 1,  "price": 35000},
    "3d":  {"label": "KEY 3 NGÀY",   "days": 3,  "price": 60000},
    "7d":  {"label": "KEY 7 NGÀY",   "days": 7,  "price": 95000},
    "1m":  {"label": "KEY 1 THÁNG",  "days": 30, "price": 175000},
    "2m":  {"label": "KEY 2 THÁNG",  "days": 60, "price": 220000},
    "3m":  {"label": "KEY 3 THÁNG",  "days": 90, "price": 270000},
}

# ── INTERNAL HELPERS ──────────────────────────
def _load(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save(path: Path, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _gen_key(plan_id: str) -> str:
    chars = string.ascii_uppercase + string.digits
    rand = ''.join(secrets.choice(chars) for _ in range(10))
    prefix = plan_id.upper()
    return f"VIP-{prefix}-{rand}"

def _now() -> int:
    return int(time.time())

def _ts_to_str(ts: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")

# ── USER OPERATIONS ───────────────────────────
def get_users() -> dict:
    return _load(USERS_FILE)

def get_user(username: str) -> dict | None:
    return get_users().get(username.lower())

def create_user(username: str, password: str, name: str) -> tuple[bool, str]:
    users = get_users()
    u = username.lower().strip()
    if len(u) < 4:
        return False, "Tên đăng nhập tối thiểu 4 ký tự"
    if len(password) < 6:
        return False, "Mật khẩu tối thiểu 6 ký tự"
    if u in users:
        return False, "Tên đăng nhập đã tồn tại"
    users[u] = {
        "username": u,
        "name": name.strip(),
        "password": _hash_pw(password),
        "created_at": _now(),
        "key_expire": None,
        "key_plan": None,
        "used_key": None,
        "balance": 0,
        "history": []
    }
    _save(USERS_FILE, users)
    _log("register", u, f"Đăng ký tài khoản: {name}")
    return True, "OK"

def verify_user(username: str, password: str) -> tuple[bool, str]:
    user = get_user(username)
    if not user:
        return False, "Tài khoản không tồn tại"
    if user["password"] != _hash_pw(password):
        return False, "Mật khẩu không đúng"
    return True, "OK"

def update_user(username: str, data: dict):
    users = get_users()
    u = username.lower()
    if u in users:
        users[u].update(data)
        _save(USERS_FILE, users)

def add_user_history(username: str, action: str):
    users = get_users()
    u = username.lower()
    if u in users:
        hist = users[u].get("history", [])
        hist.insert(0, {"action": action, "time": _ts_to_str(_now()), "ts": _now()})
        if len(hist) > 50:
            hist = hist[:50]
        users[u]["history"] = hist
        _save(USERS_FILE, users)

def user_key_active(username: str) -> bool:
    user = get_user(username)
    if not user:
        return False
    exp = user.get("key_expire")
    return bool(exp and exp > _now())

def get_key_remain_days(username: str) -> int:
    user = get_user(username)
    if not user:
        return 0
    exp = user.get("key_expire")
    if not exp or exp <= _now():
        return 0
    return max(0, int((exp - _now()) / 86400))

# ── KEY OPERATIONS ────────────────────────────
def get_keys() -> dict:
    return _load(KEYS_FILE)

def create_key(plan_id: str, created_by: str = "admin", note: str = "") -> tuple[bool, str]:
    if plan_id not in PLANS:
        return False, f"Gói không hợp lệ: {plan_id}"
    keys = get_keys()
    key = _gen_key(plan_id)
    # ensure unique
    while key in keys:
        key = _gen_key(plan_id)
    plan = PLANS[plan_id]
    keys[key] = {
        "key": key,
        "plan_id": plan_id,
        "plan_label": plan["label"],
        "days": plan["days"],
        "price": plan["price"],
        "created_at": _now(),
        "created_by": created_by,
        "used_by": None,
        "used_at": None,
        "expire_at": None,
        "note": note,
        "status": "active"  # active | used | expired
    }
    _save(KEYS_FILE, keys)
    _log("create_key", created_by, f"Tạo key {key} gói {plan['label']}")
    return True, key

def create_keys_batch(plan_id: str, count: int, created_by: str = "admin") -> tuple[bool, list]:
    result = []
    for _ in range(count):
        ok, key = create_key(plan_id, created_by)
        if ok:
            result.append(key)
    return True, result

def activate_key_for_user(key_str: str, username: str) -> tuple[bool, str]:
    keys = get_keys()
    users = get_users()
    u = username.lower()

    if key_str not in keys:
        return False, "❌ Key không hợp lệ hoặc không tồn tại"

    kdata = keys[key_str]

    if kdata["status"] == "used":
        if kdata["used_by"] == u:
            return False, "⚠️ Key này đang được dùng trên tài khoản của bạn"
        return False, "❌ Key này đã được sử dụng bởi tài khoản khác"

    if kdata["status"] == "expired":
        return False, "❌ Key đã hết hạn"

    # Check user already has active key
    if u in users:
        cur_exp = users[u].get("key_expire")
        if cur_exp and cur_exp > _now():
            # Extend instead of replace
            new_exp = cur_exp + kdata["days"] * 86400
        else:
            new_exp = _now() + kdata["days"] * 86400
    else:
        return False, "Tài khoản không tồn tại"

    # Mark key used
    keys[key_str]["used_by"] = u
    keys[key_str]["used_at"] = _now()
    keys[key_str]["expire_at"] = new_exp
    keys[key_str]["status"] = "used"
    _save(KEYS_FILE, keys)

    # Update user
    users[u]["key_expire"] = new_exp
    users[u]["key_plan"] = kdata["plan_label"]
    users[u]["used_key"] = key_str
    _save(USERS_FILE, users)

    add_user_history(u, f"Kích hoạt {kdata['plan_label']} · Key {key_str[-6:]}")
    _log("activate_key", u, f"Kích hoạt key {key_str} gói {kdata['plan_label']}")
    return True, f"✅ Kích hoạt thành công! {kdata['plan_label']} — còn {kdata['days']} ngày"

def get_key_info(key_str: str) -> dict | None:
    return get_keys().get(key_str)

def list_active_keys() -> list:
    keys = get_keys()
    return [v for v in keys.values() if v["status"] == "active"]

def list_used_keys() -> list:
    keys = get_keys()
    return [v for v in keys.values() if v["status"] == "used"]

def delete_key(key_str: str) -> bool:
    keys = get_keys()
    if key_str in keys and keys[key_str]["status"] == "active":
        del keys[key_str]
        _save(KEYS_FILE, keys)
        return True
    return False

# ── PAYMENT OPERATIONS ────────────────────────
def get_payments() -> dict:
    return _load(PAYMENTS_FILE)

def create_payment(username: str, plan_id: str, txn_code: str) -> dict:
    payments = get_payments()
    plan = PLANS[plan_id]
    pid = f"PAY-{txn_code}"
    payments[pid] = {
        "id": pid,
        "username": username,
        "plan_id": plan_id,
        "plan_label": plan["label"],
        "amount": plan["price"],
        "txn_code": txn_code,
        "status": "pending",   # pending | confirmed | rejected
        "created_at": _now(),
        "confirmed_at": None,
        "confirmed_by": None,
        "note": ""
    }
    _save(PAYMENTS_FILE, payments)
    _log("payment_create", username, f"Tạo thanh toán {pid} gói {plan['label']} {plan['price']:,}đ")
    return payments[pid]

def confirm_payment(txn_code: str, confirmed_by: str = "admin") -> tuple[bool, str, dict | None]:
    payments = get_payments()
    found = None
    for pid, p in payments.items():
        if p["txn_code"] == txn_code and p["status"] == "pending":
            found = (pid, p)
            break
    if not found:
        return False, "Không tìm thấy giao dịch pending với mã này", None
    pid, p = found
    payments[pid]["status"] = "confirmed"
    payments[pid]["confirmed_at"] = _now()
    payments[pid]["confirmed_by"] = confirmed_by
    _save(PAYMENTS_FILE, payments)

    # Auto create & activate key
    ok, key = create_key(p["plan_id"], f"auto:{confirmed_by}", f"Auto from payment {txn_code}")
    if ok:
        activate_key_for_user(key, p["username"])
        add_user_history(p["username"], f"Thanh toán xác nhận: {p['plan_label']} — {p['amount']:,}đ")
        _log("payment_confirm", confirmed_by, f"Xác nhận {pid} → key {key}")
        return True, key, payments[pid]
    return False, "Tạo key thất bại", None

def reject_payment(txn_code: str, reason: str = "", by: str = "admin") -> bool:
    payments = get_payments()
    for pid, p in payments.items():
        if p["txn_code"] == txn_code and p["status"] == "pending":
            payments[pid]["status"] = "rejected"
            payments[pid]["note"] = reason
            payments[pid]["confirmed_at"] = _now()
            payments[pid]["confirmed_by"] = by
            _save(PAYMENTS_FILE, payments)
            add_user_history(p["username"], f"Thanh toán bị từ chối: {p['plan_label']}")
            return True
    return False

def list_pending_payments() -> list:
    payments = get_payments()
    return sorted(
        [v for v in payments.values() if v["status"] == "pending"],
        key=lambda x: x["created_at"]
    )

def get_payment_by_txn(txn_code: str) -> dict | None:
    for p in get_payments().values():
        if p["txn_code"] == txn_code:
            return p
    return None

# ── STATS ─────────────────────────────────────
def get_stats() -> dict:
    users = get_users()
    keys = get_keys()
    payments = get_payments()
    active_users = sum(1 for u in users.values() if u.get("key_expire") and u["key_expire"] > _now())
    return {
        "total_users": len(users),
        "active_users": active_users,
        "total_keys": len(keys),
        "active_keys": sum(1 for k in keys.values() if k["status"] == "active"),
        "used_keys": sum(1 for k in keys.values() if k["status"] == "used"),
        "total_payments": len(payments),
        "pending_payments": sum(1 for p in payments.values() if p["status"] == "pending"),
        "confirmed_payments": sum(1 for p in payments.values() if p["status"] == "confirmed"),
        "total_revenue": sum(p["amount"] for p in payments.values() if p["status"] == "confirmed"),
    }

# ── LOGS ──────────────────────────────────────
def _log(action: str, user: str, detail: str):
    logs = _load(LOGS_FILE)
    if "logs" not in logs:
        logs["logs"] = []
    logs["logs"].insert(0, {
        "action": action,
        "user": user,
        "detail": detail,
        "time": _ts_to_str(_now()),
        "ts": _now()
    })
    if len(logs["logs"]) > 500:
        logs["logs"] = logs["logs"][:500]
    _save(LOGS_FILE, logs)

def get_logs(limit: int = 50) -> list:
    logs = _load(LOGS_FILE)
    return logs.get("logs", [])[:limit]
