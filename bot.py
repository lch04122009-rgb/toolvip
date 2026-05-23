"""
bot.py — Telegram Bot Admin
Chạy song song với Flask: python bot.py
Hoặc chạy chung: python main.py
"""
import os, asyncio, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from dotenv import load_dotenv
import db

load_dotenv()

BOT_TOKEN  = os.getenv("8547766821:AAHxHXAPqYLYWZHiDMLg78chMQeVkGySN1Y", "")
ADMIN_IDS  = [int(x.strip()) for x in os.getenv("6009450987","").split(",") if x.strip().isdigit()]
TG_SUPPORT = os.getenv("TG_SUPPORT", "@my201901")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ── ADMIN CHECK ────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def admin_only(f):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Bạn không có quyền admin.")
            return
        return await f(update, ctx)
    wrapper.__name__ = f.__name__
    return wrapper

# ── HELPERS ────────────────────────────────────
def fmt_key_block(keys: list, title: str) -> str:
    if not keys:
        return f"*{title}*\n_(Trống)_"
    lines = [f"*{title}*\n"]
    for k in keys[:20]:
        line = f"• `{k['key']}` — {k['plan_label']}"
        if k.get("used_by"):
            line += f" → @{k['used_by']}"
        lines.append(line)
    if len(keys) > 20:
        lines.append(f"... và {len(keys)-20} key khác")
    return "\n".join(lines)

def fmt_stats(s: dict) -> str:
    return (
        f"📊 *THỐNG KÊ HỆ THỐNG*\n\n"
        f"👥 Tổng users: *{s['total_users']}*\n"
        f"✅ Users đang active: *{s['active_users']}*\n"
        f"🔑 Tổng key: *{s['total_keys']}*\n"
        f"   • Còn trống: {s['active_keys']}\n"
        f"   • Đã dùng: {s['used_keys']}\n"
        f"💰 Tổng GD: *{s['total_payments']}*\n"
        f"   • Chờ xác nhận: {s['pending_payments']}\n"
        f"   • Đã xác nhận: {s['confirmed_payments']}\n"
        f"💵 Doanh thu: *{s['total_revenue']:,}đ*"
    )

# ── /start ─────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name
    if is_admin(uid):
        kb = [
            [InlineKeyboardButton("🔑 Tạo Key", callback_data="menu_create"),
             InlineKeyboardButton("📋 Xem Key", callback_data="menu_keys")],
            [InlineKeyboardButton("💰 Chờ TT", callback_data="menu_pending"),
             InlineKeyboardButton("📊 Thống kê", callback_data="menu_stats")],
            [InlineKeyboardButton("👥 Users", callback_data="menu_users"),
             InlineKeyboardButton("📜 Logs", callback_data="menu_logs")],
        ]
        await update.message.reply_text(
            f"👑 *Chào Admin {name}!*\n\n"
            f"🤖 VIP GAME Bot — Quản lý hệ thống\n"
            f"━━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"👋 Xin chào *{name}*!\n\n"
            f"🎮 *VIP GAME Tool* — Hệ thống dự đoán AI\n\n"
            f"💬 Liên hệ mua key: {TG_SUPPORT}\n"
            f"🌐 Website: https://your-app.onrender.com",
            parse_mode="Markdown"
        )

# ── /taokey ────────────────────────────────────
@admin_only
async def cmd_create_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    plans_text = "\n".join([f"  `{pid}` — {p['label']} ({p['days']} ngày) {p['price']:,}đ"
                             for pid, p in db.PLANS.items()])
    kb = [[InlineKeyboardButton(f"{p['label']}", callback_data=f"mk_{pid}")]
          for pid, p in db.PLANS.items()]
    kb.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel")])
    await update.message.reply_text(
        f"🔑 *TẠO KEY MỚI*\n\nChọn gói:\n{plans_text}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

# ── /taokey_hang_loat plan count ───────────────
@admin_only
async def cmd_batch_keys(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "📌 Cú pháp: `/batch <goi> <so_luong>`\n"
            "Ví dụ: `/batch 3d 5` — tạo 5 key 3 ngày\n\n"
            "Gói: " + " | ".join(db.PLANS.keys()),
            parse_mode="Markdown"
        )
        return
    plan_id, count_str = args[0], args[1]
    if plan_id not in db.PLANS:
        await update.message.reply_text(f"❌ Gói không hợp lệ: `{plan_id}`", parse_mode="Markdown")
        return
    try:
        count = min(int(count_str), 50)
    except ValueError:
        await update.message.reply_text("❌ Số lượng không hợp lệ")
        return
    ok, keys = db.create_keys_batch(plan_id, count, str(update.effective_user.id))
    plan = db.PLANS[plan_id]
    keys_text = "\n".join([f"`{k}`" for k in keys])
    await update.message.reply_text(
        f"✅ *Tạo {len(keys)} key {plan['label']} thành công!*\n\n{keys_text}",
        parse_mode="Markdown"
    )

# ── /confirm <txn_code> ────────────────────────
@admin_only
async def cmd_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📌 Cú pháp: `/confirm <ma_ck>`", parse_mode="Markdown")
        return
    txn = ctx.args[0].strip()
    admin_name = str(update.effective_user.id)
    ok, result, pay = db.confirm_payment(txn, admin_name)
    if ok:
        key_str = result
        # Notify user
        user = db.get_user(pay["username"])
        await update.message.reply_text(
            f"✅ *Xác nhận thành công!*\n\n"
            f"👤 User: `{pay['username']}`\n"
            f"📦 Gói: {pay['plan_label']}\n"
            f"🔑 Key tạo: `{key_str}`\n"
            f"💵 Số tiền: {pay['amount']:,}đ",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ {result}")

# ── /reject <txn_code> <ly_do> ─────────────────
@admin_only
async def cmd_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📌 Cú pháp: `/reject <ma_ck> [ly_do]`", parse_mode="Markdown")
        return
    txn = ctx.args[0].strip()
    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "Admin từ chối"
    ok = db.reject_payment(txn, reason, str(update.effective_user.id))
    if ok:
        await update.message.reply_text(f"❌ Đã từ chối GD `{txn}`\nLý do: {reason}", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Không tìm thấy GD pending với mã này")

# ── /pending ────────────────────────────────────
@admin_only
async def cmd_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending = db.list_pending_payments()
    if not pending:
        await update.message.reply_text("✅ Không có giao dịch nào đang chờ")
        return
    lines = [f"💰 *GIAO DỊCH CHỜ XÁC NHẬN* ({len(pending)})\n"]
    for p in pending[:10]:
        lines.append(
            f"━━━━━━━━━━\n"
            f"👤 `{p['username']}`\n"
            f"📦 {p['plan_label']} — {p['amount']:,}đ\n"
            f"🔑 Mã: `{p['txn_code']}`\n"
            f"⏰ {p.get('created_at_str', 'N/A')}\n"
            f"✅ `/confirm {p['txn_code']}`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /stats ──────────────────────────────────────
@admin_only
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(fmt_stats(s), parse_mode="Markdown")

# ── /keys ───────────────────────────────────────
@admin_only
async def cmd_keys(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    active = db.list_active_keys()
    text = fmt_key_block(active, f"🔑 KEY CÒN TRỐNG ({len(active)})")
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /user <username> ────────────────────────────
@admin_only
async def cmd_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("📌 Cú pháp: `/user <username>`", parse_mode="Markdown")
        return
    uname = ctx.args[0].lower()
    user = db.get_user(uname)
    if not user:
        await update.message.reply_text(f"❌ Không tìm thấy user: `{uname}`", parse_mode="Markdown")
        return
    active = db.user_key_active(uname)
    remain = db.get_key_remain_days(uname)
    await update.message.reply_text(
        f"👤 *USER INFO*\n\n"
        f"Tên: {user['name']}\n"
        f"User: `{uname}`\n"
        f"Key: {'✅ Active' if active else '❌ Inactive'}\n"
        f"Gói: {user.get('key_plan') or 'N/A'}\n"
        f"Còn: {remain} ngày\n"
        f"Key dùng: `{user.get('used_key') or 'N/A'}`",
        parse_mode="Markdown"
    )

# ── /addkey <username> <plan> ───────────────────
@admin_only
async def cmd_addkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "📌 Cú pháp: `/addkey <username> <goi>`\n"
            "Ví dụ: `/addkey hoan 7d`",
            parse_mode="Markdown"
        )
        return
    uname, plan_id = ctx.args[0].lower(), ctx.args[1]
    if not db.get_user(uname):
        await update.message.reply_text(f"❌ User không tồn tại: `{uname}`", parse_mode="Markdown")
        return
    ok, key = db.create_key(plan_id, str(update.effective_user.id), f"Admin gift to {uname}")
    if not ok:
        await update.message.reply_text(f"❌ {key}")
        return
    ok2, msg = db.activate_key_for_user(key, uname)
    if ok2:
        await update.message.reply_text(
            f"✅ *Đã tặng key cho `{uname}`*\n🔑 Key: `{key}`\n📦 Gói: {db.PLANS[plan_id]['label']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ {msg}")

# ── /logs ───────────────────────────────────────
@admin_only
async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logs = db.get_logs(20)
    if not logs:
        await update.message.reply_text("Chưa có log")
        return
    lines = ["📜 *LOG GẦN ĐÂY*\n"]
    for l in logs[:15]:
        lines.append(f"• [{l['time']}] `{l['action']}` — {l['user']}: {l['detail'][:50]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ── /help ───────────────────────────────────────
@admin_only
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *LỆNH ADMIN*\n\n"
        "🔑 *Quản lý key:*\n"
        "`/taokey` — Tạo 1 key (chọn gói)\n"
        "`/batch <goi> <sl>` — Tạo hàng loạt\n"
        "`/keys` — Xem key còn trống\n"
        "`/addkey <user> <goi>` — Tặng key cho user\n\n"
        "💰 *Thanh toán:*\n"
        "`/pending` — Xem GD chờ xác nhận\n"
        "`/confirm <ma>` — Xác nhận GD\n"
        "`/reject <ma> [ly_do]` — Từ chối GD\n\n"
        "👥 *User:*\n"
        "`/user <username>` — Xem info user\n\n"
        "📊 *Hệ thống:*\n"
        "`/stats` — Thống kê\n"
        "`/logs` — Log hệ thống",
        parse_mode="Markdown"
    )

# ── CALLBACK BUTTONS ────────────────────────────
async def cb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "cancel":
        await q.edit_message_text("❌ Đã hủy")
        return

    if data == "menu_stats":
        s = db.get_stats()
        await q.edit_message_text(fmt_stats(s), parse_mode="Markdown")
        return

    if data == "menu_pending":
        pending = db.list_pending_payments()
        if not pending:
            await q.edit_message_text("✅ Không có GD nào đang chờ")
            return
        lines = [f"💰 *CHỜ XÁC NHẬN* ({len(pending)})\n"]
        for p in pending[:8]:
            lines.append(f"• `{p['username']}` — {p['plan_label']} — `{p['txn_code']}`")
        lines.append("\n✅ `/confirm <ma_ck>`")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown")
        return

    if data == "menu_keys":
        active = db.list_active_keys()
        text = fmt_key_block(active, f"🔑 KEY CÒN TRỐNG ({len(active)})")
        await q.edit_message_text(text, parse_mode="Markdown")
        return

    if data == "menu_users":
        users = db.get_users()
        lines = [f"👥 *USERS ({len(users)})*\n"]
        for uname, u in list(users.items())[:15]:
            active = db.user_key_active(uname)
            remain = db.get_key_remain_days(uname)
            status = f"✅ {remain}ngày" if active else "❌"
            lines.append(f"• `{uname}` — {u['name']} — {status}")
        await q.edit_message_text("\n".join(lines), parse_mode="Markdown")
        return

    if data == "menu_logs":
        logs = db.get_logs(15)
        lines = ["📜 *LOGS*\n"]
        for l in logs:
            lines.append(f"• `{l['action']}` {l['user']}: {l['detail'][:40]}")
        await q.edit_message_text("\n".join(lines) if logs else "Chưa có log", parse_mode="Markdown")
        return

    if data == "menu_create":
        kb = [[InlineKeyboardButton(f"{p['label']} — {p['price']:,}đ", callback_data=f"mk_{pid}")]
              for pid, p in db.PLANS.items()]
        kb.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel")])
        await q.edit_message_text(
            "🔑 *Chọn gói để tạo key:*",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return

    if data.startswith("mk_"):
        plan_id = data[3:]
        if plan_id not in db.PLANS:
            await q.edit_message_text("❌ Gói không hợp lệ")
            return
        ok, key = db.create_key(plan_id, str(q.from_user.id))
        if ok:
            plan = db.PLANS[plan_id]
            kb = [[InlineKeyboardButton("🔑 Tạo thêm", callback_data=f"mk_{plan_id}"),
                   InlineKeyboardButton("📋 Xem tất cả", callback_data="menu_keys")]]
            await q.edit_message_text(
                f"✅ *Tạo key thành công!*\n\n"
                f"🔑 Key: `{key}`\n"
                f"📦 Gói: {plan['label']}\n"
                f"📅 {plan['days']} ngày — {plan['price']:,}đ",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(f"❌ {key}")
        return

# ── RUN BOT ─────────────────────────────────────
def run_bot():
    if not BOT_TOKEN:
        print("⚠️  BOT_TOKEN chưa được set. Bot sẽ không chạy.")
        return
    if not ADMIN_IDS:
        print("⚠️  ADMIN_IDS chưa được set. Chức năng admin sẽ bị từ chối.")

    app_bot = Application.builder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CommandHandler("taokey", cmd_create_key))
    app_bot.add_handler(CommandHandler("batch", cmd_batch_keys))
    app_bot.add_handler(CommandHandler("confirm", cmd_confirm))
    app_bot.add_handler(CommandHandler("reject", cmd_reject))
    app_bot.add_handler(CommandHandler("pending", cmd_pending))
    app_bot.add_handler(CommandHandler("stats", cmd_stats))
    app_bot.add_handler(CommandHandler("keys", cmd_keys))
    app_bot.add_handler(CommandHandler("user", cmd_user))
    app_bot.add_handler(CommandHandler("addkey", cmd_addkey))
    app_bot.add_handler(CommandHandler("logs", cmd_logs))
    app_bot.add_handler(CommandHandler("help", cmd_help))
    app_bot.add_handler(CallbackQueryHandler(cb_handler))

    print("🤖 Telegram Bot started!")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    run_bot()
