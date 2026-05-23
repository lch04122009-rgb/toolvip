import os
import sys
import time
from tabulate import tabulate

try:
    import db
except ImportError:
    print("❌ Lỗi: Không tìm thấy file 'db.py' trong cùng thư mục!")
    print("Vui lòng đặt file này nằm chung thư mục với file db.py của hệ thống.")
    input("\nNhấn Enter để thoát...")
    sys.exit()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    print("=" * 60)
    print(f" {title.center(58)} ")
    print("=" * 60)

def show_stats():
    clear_screen()
    print_header("📊 THỐNG KÊ HỆ THỐNG THỰC TẾ")
    s = db.get_stats()
    
    table_data = [
        ["👥 Tổng người dùng thành viên", f"{s['total_users']} tài khoản"],
        ["🟢 Thành viên VIP đang kích hoạt", f"{s['active_users']} tài khoản"],
        ["🔑 Tổng số Key đã tạo", f"{s['total_keys']} key"],
        ["   • Key chưa sử dụng (Trống)", f"{s['active_keys']} key"],
        ["   • Key đã kích hoạt", f"{s['used_keys']} key"],
        ["💳 Tổng số đơn nạp tiền (GD)", f"{s['total_payments']} đơn"],
        ["   • Đơn đang chờ xác nhận (Pending)", f"{s['pending_payments']} đơn"],
        ["   • Đơn đã duyệt thành công", f"{s['confirmed_payments']} đơn"],
        ["💰 TỔNG DOANH THU HỆ THỐNG", f"{s['total_revenue']:,} VNĐ"]
    ]
    print(tabulate(table_data, headers=["Hạng mục", "Số liệu thực tế"], tablefmt="fancy_grid"))
    input("\n[Nhấn Enter để quay lại Menu chính]")

def create_key_menu():
    while True:
        clear_screen()
        print_header("🔑 TẠO KEY VIP HỆ THỐNG")
        
        plans_list = []
        for pid, p in db.PLANS.items():
            plans_list.append([pid, p['label'], f"{p['days']} ngày", f"{p['price']:,}đ"])
        
        print(tabulate(plans_list, headers=["Mã Gói", "Tên Gói", "Thời hạn", "Giá tiền"], tablefmt="simple"))
        print("-" * 60)
        
        pid_choice = input("👉 Nhập [Mã Gói] muốn tạo (hoặc gõ '0' để quay lại): ").strip().lower()
        if pid_choice == '0':
            break
            
        if pid_choice not in db.PLANS:
            print("❌ Mã gói không hợp lệ! Vui lòng thử lại.")
            time.sleep(1.5)
            continue
            
        count_str = input("🔢 Nhập số lượng key muốn tạo (Mặc định 1, tối đa 50): ").strip()
        count = 1
        if count_str:
            try:
                count = min(max(int(count_str), 1), 50)
            except ValueError:
                print("❌ Số lượng phải là số nguyên!")
                time.sleep(1.5)
                continue
        
        ok, keys = db.create_keys_batch(pid_choice, count, created_by="CMD_Console")
        if ok and keys:
            print(f"\n✅ Đã tạo thành công {len(keys)} key cho gói [{db.PLANS[pid_choice]['label']}]:")
            for k in keys:
                print(f" ➡️  Key: \033[92m{k}\033[0m")
            print("\n[Dữ liệu đã tự động lưu trực tiếp vào file keys.json]")
        else:
            print(f"❌ Thất bại: {keys}")
            
        input("\n[Nhấn Enter để tiếp tục]")
        break

def manage_pending_payments():
    while True:
        clear_screen()
        print_header("⏳ DANH SÁCH ĐƠN NẠP TIỀN CHỜ DUYỆT")
        
        pending_list = db.list_pending_payments()
        if not pending_list:
            print("📭 Hiện tại không có hóa đơn nạp tiền nào đang chờ duyệt trên hệ thống.")
            input("\n[Nhấn Enter để quay lại Menu chính]")
            break
            
        table_rows = []
        for idx, p in enumerate(pending_list, start=1):
            time_str = db._ts_to_str(p['created_at']) if hasattr(db, '_ts_to_str') else str(p['created_at'])
            table_rows.append([
                idx, 
                p['username'], 
                p['plan_label'], 
                f"{p['amount']:,}đ", 
                p['txn_code'],
                time_str
            ])
            
        print(tabulate(table_rows, headers=["STT", "Tài khoản", "Gói mua", "Số tiền", "Mã CK (TXN)", "Thời gian"], tablefmt="fancy_grid"))
        print("\n[Hành động]: Nhập số STT đơn muốn xử lý, hoặc gõ '0' để quay lại.")
        
        choice = input("👉 Chọn đơn cần xử lý: ").strip()
        if choice == '0':
            break
            
        try:
            selected_idx = int(choice) - 1
            if selected_idx < 0 or selected_idx >= len(pending_list):
                raise ValueError
        except ValueError:
            print("❌ Lựa chọn không hợp lệ!")
            time.sleep(1.5)
            continue
            
        selected_pay = pending_list[selected_idx]
        txn = selected_pay['txn_code']
        
        print(f"\n--- Đang xử lý giao dịch [{txn}] của User [{selected_pay['username']}] ---")
        print("1. [✅ DUYỆT] Xác nhận đã nhận tiền -> Tự động cấp gia hạn VIP")
        print("2. [❌ HỦY] Từ chối đơn nạp tiền này")
        print("3. Bỏ qua (Quay lại)")
        
        act = input("👉 Chọn hành động (1/2/3): ").strip()
        if act == '1':
            ok, result, pay_data = db.confirm_payment(txn, confirmed_by="CMD_Console")
            if ok:
                print(f"\n✅ DUYỆT THÀNH CÔNG! Đã sinh key VIP: {result} và nạp thẳng cho user.")
            else:
                print(f"\n❌ Lỗi: {result}")
            time.sleep(2)
        elif act == '2':
            reason = input("💬 Nhập lý do từ chối (bỏ trống nếu muốn): ").strip() or "Admin hủy thủ công qua CMD"
            ok = db.reject_payment(txn, reason, by="CMD_Console")
            if ok:
                print("\n❌ Đã hủy bỏ đơn nạp tiền thành công.")
            else:
                print("\n❌ Không tìm thấy hoặc đơn đã bị thay đổi trạng thái.")
            time.sleep(2)

def show_logs():
    clear_screen()
    print_header("📜 LOGS LỊCH SỬ HỆ THỐNG GẦN ĐÂY")
    
    logs = db.get_logs(30)
    if not logs:
        print("Trống — Hệ thống chưa ghi nhận log nào.")
    else:
        log_rows = []
        for l in logs:
            log_rows.append([l['time'], l['user'], l['action'], l['detail'][:50]])
        print(tabulate(log_rows, headers=["Thời gian", "Tác nhân", "Hành động", "Chi tiết ngắn"], tablefmt="simple"))
        
    input("\n[Nhấn Enter để quay lại Menu chính]")

def main_menu():
    while True:
        clear_screen()
        print("============================================================")
        print("👑  VIP GAME SYSTEM — TRÌNH QUẢN TRỊ ADMIN ĐỘC LẬP TRÊN CMD ")
        print("============================================================")
        print(" 1. 📊 Xem số liệu thống kê hệ thống thực tế")
        print(" 2. 🔑 Tạo và xuất Key VIP hệ thống (Đơn lẻ / Hàng loạt)")
        print(" 3. ⏳ Duyệt / Từ chối đơn nạp tiền đang chờ (Pending)")
        print(" 4. 📜 Xem lịch sử Logs hệ thống")
        print(" 5. ❌ Thoát chương trình")
        print("============================================================")
        
        choice = input("👉 Mời Admin chọn chức năng (1-5): ").strip()
        
        if choice == '1':
            show_stats()
        elif choice == '2':
            create_key_menu()
        elif choice == '3':
            manage_pending_payments()
        elif choice == '4':
            show_logs()
        elif choice == '5':
            print("\n👋 Đang đóng trình quản trị. Tạm biệt Admin!")
            break
        else:
            print("❌ Lựa chọn không hợp lệ! Vui lòng nhập từ 1 đến 5.")
            time.sleep(1.5)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 Đã thoát chương trình đột ngột.")
