"""
pump_ml.py
==========
Bơm đúng số gram mong muốn chỉ dùng thông số calib — KHÔNG cần loadcell.

Công thức:
    t = (gram_target - b) / a
    → Chạy bơm đúng t giây rồi tắt.

Cách dùng độc lập:
    python pump_ml.py

Cách import vào file khác:
    from pump_ml import pump_gram, pump_gram_multi
"""

import json
from time import sleep

from gpiozero import PWMLED

from configuration.configuration import PUMP_CALIB_FILE
from configuration.configuration import CALIBLOADCELL_FILE

# ── CẤU HÌNH ─────────────────────────────────────────────────────────────────
PUMP_GPIO = {
    1: 26,
    2: 15,
    3: 21,
    4: 20,
    5: 16,
    6: 12,
    7: 13,
    8: 6,
    9: 5,
    10: 14,
}


# ══════════════════════════════════════════════════════════════════════════════
# LOAD THÔNG SỐ CALIB
# ══════════════════════════════════════════════════════════════════════════════

def _load_pump_calib() -> dict:
    try:
        with open(PUMP_CALIB_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Khong tim thay '{PUMP_CALIB_FILE}'. "
            f"Hay chay calib_pump.py truoc."
        )


# ══════════════════════════════════════════════════════════════════════════════
# HÀM CHÍNH: BƠM MỘT BƠM
# ══════════════════════════════════════════════════════════════════════════════

def pump_gram(
    pump_number: int,
    gram_target: float,
    verbose: bool = True,
) -> float:
    """
    Bơm đúng gram_target gram dựa trên thông số calib.
    Không cần loadcell — chỉ dùng sleep().

    Tham số:
        pump_number  — số bơm (1..10)
        gram_target  — số gram muốn bơm (ví dụ: 200.0)
        verbose      — True = in log, False = im lặng

    Trả về:
        float — số giây đã chạy bơm
    """
    pump_calib = _load_pump_calib()
    key = f"pump_{pump_number}"

    if key not in pump_calib:
        raise ValueError(
            f"Bom #{pump_number} chua duoc calib. "
            f"Chay calib_pump.py roi chon bom {pump_number}."
        )
    if pump_number not in PUMP_GPIO:
        raise ValueError(f"Bom #{pump_number} khong co trong bang PUMP_GPIO.")

    d = pump_calib[key]
    a = d["gram_per_sec"]   # tốc độ thực (g/s)
    b = d["dead_gram"]      # dead zone (g)

    # t = (gram_target - b) / a
    duration = (gram_target - b) / a
    if duration <= 0:
        raise ValueError(
            f"Thoi gian tinh ra am ({duration:.3f}s). "
            f"Kiem tra lai thong so calib bom #{pump_number}."
        )

    gpio_pin = PUMP_GPIO[pump_number]
    pwm = PWMLED(gpio_pin, frequency=1000)

    if verbose:
        print(f"  [Bom #{pump_number}] {gram_target:.1f}g → chay {duration:.3f}s  "
              f"(a={a:.4f} b={b:.4f})")

    try:
        pwm.value = 1.0
        sleep(duration)
        pwm.off()
    except Exception:
        pwm.off()
        raise
    finally:
        pwm.off()

    if verbose:
        print(f"  [Bom #{pump_number}] Xong.")

    return duration


# ══════════════════════════════════════════════════════════════════════════════
# HÀM PHỤ: BƠM NHIỀU BƠM TUẦN TỰ
# ══════════════════════════════════════════════════════════════════════════════

def pump_gram_multi(
    orders: list[tuple[int, float]],
    verbose: bool = True,
) -> list[float]:
    """
    Bơm nhiều bơm tuần tự (một cái xong rồi mới đến cái tiếp theo).

    Tham số:
        orders  — danh sách [(pump_number, gram_target), ...]
                  ví dụ: [(1, 150.0), (3, 80.0), (2, 200.0)]
        verbose — in log hay không

    Trả về:
        list[float] — thời gian chạy (giây) của từng bơm

    Ví dụ:
        pump_gram_multi([(1, 200), (2, 100)])
        # Bơm #1 chạy 200g xong → Bơm #2 chạy 100g
    """
    results = []
    for idx, (pump_number, gram_target) in enumerate(orders):
        if verbose:
            print(f"\n  ({idx+1}/{len(orders)}) Bom #{pump_number} → {gram_target:.1f}g")
        t = pump_gram(pump_number, gram_target, verbose=verbose)
        results.append(t)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CHẠY THỬ TRỰC TIẾP
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("  THU NGHIEM BOM")
    print("=" * 50)

    print("\n  Nhap lenh theo dinh dang:  <so_bom> <gram>")
    print("  Vi du:  1 200        → Bom #1 bom 200g")
    print("  Vi du:  1 150 3 80   → Bom #1 bom 150g, roi Bom #3 bom 80g")
    print("  Nhap 'q' de thoat.\n")

    while True:
        raw = input("  Lenh > ").strip().lower()
        if raw == "q":
            break

        tokens = raw.split()
        if len(tokens) < 2 or len(tokens) % 2 != 0:
            print("  Sai dinh dang. Vi du: 1 200  hoac  1 150 3 80")
            continue

        orders = []
        valid = True
        for i in range(0, len(tokens), 2):
            try:
                p = int(tokens[i])
                g = float(tokens[i + 1])
                orders.append((p, g))
            except ValueError:
                print(f"  Gia tri khong hop le: '{tokens[i]}' '{tokens[i+1]}'")
                valid = False
                break

        if not valid:
            continue

        pump_gram_multi(orders)
