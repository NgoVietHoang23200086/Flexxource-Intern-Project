from gpiozero import OutputDevice, DigitalInputDevice
from time import sleep
import collections
import statistics
import json
import os

from configuration.configuration import *

# --- CẤU HÌNH PIN ---
SCK = OutputDevice(4)
DT = DigitalInputDevice(18)
SCK.off()

# --- BIẾN TOÀN CỤC ---
OFFSET = 0
SCALE = 1.0
WINDOW_SIZE = 8

# --- CẤU HÌNH BỘ LỌC SPIKE ---
SPIKE_THRESHOLD_GRAM = 15.0   # Gram lệch tối đa so với median → nếu vượt quá = spike
MAX_CONSECUTIVE_REJECTS = 5   # Reject liên tiếp tối đa trước khi chấp nhận giá trị mới
_consecutive_rejects = 0


def read_hx711():
    count = 0
    wait_limit = 100
    while DT.value == 1:
        sleep(0.0001)
        wait_limit -= 1
        if wait_limit < 0:
            return None

    for _ in range(24):
        SCK.on()
        count = count << 1
        SCK.off()
        if DT.value:
            count += 1

    SCK.on()
    SCK.off()
    if count & 0x800000:
        count -= 0x1000000
    return count


def tare(samples=30):
    """Lấy mẫu để thiết lập điểm 0 (trừ bì)"""
    global OFFSET
    data = []
    while len(data) < samples:
        v = read_hx711()
        if v is not None:
            data.append(v)
    if data:
        OFFSET = sum(data) / len(data)
    return OFFSET


def load_calibration(calib_file=CALIBLOADCELL_FILE):
    """Tải OFFSET và SCALE từ file calib đã lưu sẵn"""
    global OFFSET, SCALE
    if not os.path.exists(calib_file):
        raise FileNotFoundError(
            f"Khong tim thay '{calib_file}'. Hay chay init_loadcell.py truoc."
        )
    with open(calib_file) as f:
        d = json.load(f)
    OFFSET = float(d["offset"])
    SCALE  = float(d["scale"])


def read_weight_smooth(window):
    """
    Đọc loadcell, lọc spike, trả về gram.

    Thuật toán:
        1. Đọc raw từ HX711
        2. Nếu window đã có >= 4 mẫu, tính median hiện tại:
           - Nếu raw mới lệch > SPIKE_THRESHOLD_GRAM → bỏ qua, trả về median
           - Nếu reject liên tiếp > MAX_CONSECUTIVE_REJECTS → chấp nhận
             (tránh kẹt khi cân thật sự thay đổi nhanh)
        3. Thêm raw vào window, trả về median (thay vì mean)
    """
    global _consecutive_rejects

    raw = read_hx711()
    if raw is None:
        return None

    if SCALE == 0:
        return 0.0

    # Spike gate
    if len(window) >= 4:
        current_median_raw = statistics.median(window)
        current_gram = (current_median_raw - OFFSET) / SCALE
        new_gram     = (raw - OFFSET) / SCALE
        delta        = abs(new_gram - current_gram)

        if delta > SPIKE_THRESHOLD_GRAM and _consecutive_rejects < MAX_CONSECUTIVE_REJECTS:
            _consecutive_rejects += 1
            return current_gram  # Giữ nguyên giá trị ổn định
        else:
            _consecutive_rejects = 0
    else:
        _consecutive_rejects = 0

    window.append(raw)
    return (statistics.median(window) - OFFSET) / SCALE


# --- CHƯƠNG TRÌNH CHÍNH (chỉ chạy khi gọi trực tiếp file này) ---
if __name__ == "__main__":
    try:
        print("Dang tai thong so calib...")
        load_calibration()
        print("OK.\n")

        input("👉 Dat LY TRONG len can, roi nhan Enter...")

        print("Dang tru bi ly...", end=" ", flush=True)
        tare(30)
        print("xong!\n")

        print("Rot nuoc vao ly. Nhan Ctrl+C de dung.\n")

        window = collections.deque(maxlen=WINDOW_SIZE)

        while True:
            weight = read_weight_smooth(window)
            if weight is not None:
                if abs(weight) < 0.1:
                    weight = 0.0
                print(f"\r  Nuoc: {weight:8.2f} g", end="", flush=True)
            sleep(0.05)

    except KeyboardInterrupt:
        print("\n\nDa dung.")