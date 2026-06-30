"""
app_rot_nuoc.py
===============
Sử dụng các hàm từ thư viện loadcell.py
"""

import time
import collections
from time import sleep

# Import từ thư viện loadcell của bạn
from loadcell import load_calibration, tare, read_hx711, read_weight_smooth, WINDOW_SIZE

# ── NGƯỠNG PHÁT HIỆN LY ───────────────────────────────────────────────────────
CUP_DETECT_GRAM  = 10.0
SUSTAINED_TIME   = 1.0   # giây
IDLE_NOISE_FLOOR = 5.0   # gram

# ══════════════════════════════════════════════════════════════════════════════
# FLOW PHÁT HIỆN LY
# ══════════════════════════════════════════════════════════════════════════════

def wait_for_cup():
    # [1] In ra "Dat ly len can"
    print("\n1. Dat ly len can...")
    
    window = collections.deque(maxlen=WINDOW_SIZE)
    sustained_start = None

    while True:
        gram = read_weight_smooth(window)
        if gram is None:
            sleep(0.05)
            continue

        # Lọc nhiễu vặt (gió, nước đọng)
        if abs(gram) < IDLE_NOISE_FLOOR:
            gram = 0.0

        if gram <= CUP_DETECT_GRAM:
            sustained_start = None
        else:
            if sustained_start is None:
                sustained_start = time.monotonic()

            elapsed = time.monotonic() - sustained_start
            if elapsed >= SUSTAINED_TIME:
                return gram

        sleep(0.05)

# ══════════════════════════════════════════════════════════════════════════════
# CHƯƠNG TRÌNH CHÍNH
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        print("=" * 50)
        print("  HE THONG CAN LY — KHOI DONG")
        print("=" * 50)
        
        # Load calibration trước khi làm gì khác
        load_calibration(CALIBLOADCELL_FILE)

        # BƯỚC 1 & BƯỚC 2: Yêu cầu đặt ly và xác nhận
        wait_for_cup()
        input("2. Phat hien dat ly len can - nhan enter de confirm")

        # BƯỚC 3: Thực hiện trừ bì ly
        print("3. Dang tru bi ly...", end=" ", flush=True)
        tare(30)
        print("xong!")

        # Xả bộ đệm cũ để cân không bị âm nháy loạn
        window = collections.deque(maxlen=WINDOW_SIZE)
        for _ in range(WINDOW_SIZE * 2):
            read_weight_smooth(window)

        # ── SẴN SÀNG RÓT NƯỚC ─────────────────────────────────────────────────
        print("\n" + "=" * 50)
        print("  [OK] SAN SANG ROT NUOC")
        print("=" * 50 + "\n")

        print("  Do khoi luong nuoc real-time (Ctrl+C de dung)...\n")
        
        while True:
            gram = read_weight_smooth(window)
            if gram is not None:
                display = 0.0 if abs(gram) < 1.0 else gram
                bar     = "█" * min(int(display / 5), 40)
                print(f"\r  {display:7.2f} g  [{bar:<40}]", end="", flush=True)
            sleep(0.05)

    except KeyboardInterrupt:
        print("\n\nDa dung chuong trinh. Tam biet!")