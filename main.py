"""
main.py — Entry point cho Render
Chạy Flask API + Telegram Bot trong cùng 1 process
"""
import threading, os
from dotenv import load_dotenv
load_dotenv()

def run_flask():
    from app import app
    port = int(os.getenv("PORT", 5000))
    print(f"🌐 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def run_bot():
    try:
        from bot import run_bot as _run
        _run()
    except Exception as e:
        print(f"⚠️  Bot error: {e}")

if __name__ == "__main__":
    # Flask in main thread (Render cần main thread)
    bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
    bot_thread.start()
    print("🤖 Bot thread started")
    run_flask()
