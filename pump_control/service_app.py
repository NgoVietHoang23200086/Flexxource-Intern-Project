"""
app_ban_hang.py
===============
Chạy luồng bán hàng liên tục.
Tái sử dụng hàm wait_for_cup từ file tare.py
"""

import time
import collections
from time import sleep

# Import các hàm kỹ thuật từ thư viện loadcell.py
from loadcell import load_calibration, tare, WINDOW_SIZE
from loadcell.loadcell_robust import read_weight_robust as read_weight_smooth

# IMPORT TỪ FILE TARE.PY CỦA BẠN
from tare import wait_for_cup

# ── CẤU HÌNH NGƯỠNG RÓT NƯỚC VÀ LẤY LY ─────────────────────────────────────────
POUR_MIN_GRAM    = 10.0  # Phải rót ít nhất 10g mới tính là đang rót
STABLE_TIME      = 5.0   # Nước đứng yên 2 giây -> Xác nhận xong đơn
REMOVAL_GRAM     = -5.0  # Khối lượng tụt xuống âm 5g -> Đã lấy ly ra


def clear_buffer(window):
    """Xả bộ đệm để làm sạch dữ liệu cũ, chống nháy số ảo"""
    window.clear()
    for _ in range(WINDOW_SIZE * 2):
        read_weight_smooth(window)

# ══════════════════════════════════════════════════════════════════════════════
# CÁC BƯỚC THEO DÕI NƯỚC
# ══════════════════════════════════════════════════════════════════════════════

def wait_for_pouring(window):
    """Theo dõi real-time và tự động chốt khi rót xong"""
    print("\n  [SAN SANG ROT NUOC]...")
    poured = False
    stable_start = None
    last_weight = 0.0

    while True:
        gram = read_weight_smooth(window)
        if gram is None: continue

        # Làm tròn để hiển thị mượt hơn
        display = 0.0 if abs(gram) < 1.0 else gram
        bar = "█" * min(int(display / 5), 40)
        print(f"\r  Nuoc: {display:7.2f} g  [{bar:<40}]", end="", flush=True)

        # 1. Phát hiện bắt đầu rót nước (> 10g)
        if not poured and gram > POUR_MIN_GRAM:
            poured = True
            last_weight = gram

        # 2. Theo dõi độ ổn định để dừng
        if poured:
            # Nếu chênh lệch < 2g tức là nước đang ổn định, không rót thêm
            if abs(gram - last_weight) < 5.0:
                if stable_start is None:
                    stable_start = time.monotonic()
                elif time.monotonic() - stable_start >= STABLE_TIME:
                    print("\n")
                    return gram # Đã rót xong
            else:
                # Đang tiếp tục rót -> reset lại thời gian ổn định
                stable_start = None
                last_weight = gram

        sleep(0.05)


def wait_for_removal(window):
    """Chờ đến khi ly được nhấc ra khỏi cân"""
    print("4. Vui long lay ly ra khoi can...")
    while True:
        gram = read_weight_smooth(window)
        if gram is None: continue
        
        # Vì đã trừ bì ly, nhấc ra sẽ làm tổng về số âm
        if gram < REMOVAL_GRAM:
            return
        sleep(0.05)


# ══════════════════════════════════════════════════════════════════════════════
# VÒNG LẶP CHÍNH (MAIN LOOP)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        print("=" * 50)
        print("  HE THONG BAN HANG TU DONG — KHOI DONG")
        print("=" * 50)
        
        load_calibration("calib.json")
        window = collections.deque(maxlen=WINDOW_SIZE)
        
        # Tare lần đầu để lấy điểm 0 tuyệt đối cho bàn cân trống
        print("  Dang thiet lap diem 0 cho ban can trong...")
        tare(30)
        clear_buffer(window)

        don_hang = 1

        # Vòng lặp vĩnh cửu cho các đơn hàng
        while True:
            print("\n" + "═" * 50)
            print(f"  DON HANG #{don_hang}")
            print("═" * 50)

            # [BƯỚC 1]: Chờ đặt ly (Sử dụng lại logic từ tare.py)
            wait_for_cup()
            
            # [BƯỚC 2]: Xác nhận
            input("2. Phat hien dat ly len can - nhan enter de confirm")

            # [BƯỚC 3]: Trừ bì ly
            print("3. Dang tru bi ly...", end=" ", flush=True)
            tare(30)
            clear_buffer(window)
            print("xong!")

            # [BƯỚC 4]: Rót nước và tự động phát hiện xong
            final_weight = wait_for_pouring(window)

            # [BƯỚC 5]: In hoàn thành đơn hàng
            print("=" * 50)
            print(f" ⭐ DA HOAN THANH DON HANG ({final_weight:.1f} g) ⭐")
            print("=" * 50)

            # [BƯỚC 6]: Phát hiện ly được lấy ra
            wait_for_removal(window)
            print("  [OK] Da lay ly ra.")

            # [BƯỚC 7]: Reset (Tare) lại bàn cân trống cho đơn tiếp theo
            print("  Dang reset lai ban can...", end=" ", flush=True)
            sleep(1) # Đợi 1 nhịp cho bàn cân hết rung rắc sau khi nhấc ly
            tare(30)
            clear_buffer(window)
            print("xong! Quay lai trang thai doi dat ly...")
            
            don_hang += 1

    except KeyboardInterrupt:
        print("\n\nDa dung chuong trinh. Tam biet!")