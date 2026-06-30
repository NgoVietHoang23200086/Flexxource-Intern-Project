"""
calib_pump.py
=============
Hiệu chuẩn tốc độ bơm bằng loadcell — CLOSED LOOP + LINEAR REGRESSION.

Nguyên lý:
    - Bơm tự động tắt khi loadcell đạt target
    - Đo nhiều mốc (100g, 200g, 300g, 400g) trên cùng một ly
    - Linear regression ra: gram = a × giây + b
        + a = tốc độ thực (gram/giây)
        + b = dead zone (nước vẫn chảy sau khi tắt, lag vật lý)
    - Khi dùng thực tế: tắt bơm sớm hơn b gram để bù lag

Cách dùng:
    python calib_pump.py

Yêu cầu:
    - calib.json phải tồn tại (đã chạy init_scale.py)
    - Ly đủ lớn chứa ít nhất 450ml
    - Vòi bơm đặt vào ly trước khi bắt đầu
"""

import json
import time
import collections
import statistics
from time import sleep

# ── KHÔNG THAY ĐỔI GÌ — dùng đúng thư viện cũ ───────────────────────────────
from gpiozero import PWMLED
from loadcell.loadcell import (
    load_calibration,
    tare,
    WINDOW_SIZE,
)
from loadcell.loadcell_robust import read_weight_robust
from configuration.configuration import *

# Ánh xạ bơm → GPIO, copy y chang từ pump_control.py
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

# Các mốc target để đo (gram) — càng nhiều mốc càng chính xác regression
CALIB_TARGETS_GRAM = [100, 200, 300, 400]

# Ngưỡng ổn định sau khi tắt bơm
SETTLE_WINDOW_SIZE = 10    # Số mẫu kiểm tra
SETTLE_THRESHOLD   = 0.5   # std < ngưỡng này = nước đã đứng yên
SETTLE_TIMEOUT     = 5.0   # Tối đa chờ bao nhiêu giây

# Tắt bơm sớm hơn target bao nhiêu gram (bù lag nước trong ống)
# Regression sẽ tự tính dead_gram chính xác hơn sau khi đo xong
EARLY_STOP_GRAM = 4.0


# ══════════════════════════════════════════════════════════════════════════════
# TIỆN ÍCH
# ══════════════════════════════════════════════════════════════════════════════

def clear_buffer(window):
    """Xả bộ đệm dữ liệu cũ — copy từ service_app.py"""
    window.clear()
    for _ in range(WINDOW_SIZE * 2):
        read_weight_robust(window)


def read_stable_weight(window, timeout=SETTLE_TIMEOUT):
    """
    Chờ nước ổn định rồi đọc khối lượng.
    Trả về mean khi std của SETTLE_WINDOW_SIZE mẫu gần nhất < SETTLE_THRESHOLD.
    """
    settle_buf = collections.deque(maxlen=SETTLE_WINDOW_SIZE)
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        g = read_weight_robust(window)
        if g is not None:
            settle_buf.append(g)
            if len(settle_buf) == SETTLE_WINDOW_SIZE:
                if statistics.stdev(settle_buf) < SETTLE_THRESHOLD:
                    return statistics.mean(settle_buf)
        sleep(0.05)

    # Timeout — trả về trung bình những gì có
    return statistics.mean(settle_buf) if settle_buf else None


def linear_regression(xs, ys):
    """
    Hồi quy tuyến tính: y = a*x + b
    xs = thời gian chạy bơm (giây)
    ys = gram đo được sau khi nước ổn định
    Trả về (a, b, r_squared)
    """
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_yy = sum((y - mean_y) ** 2 for y in ys)

    if ss_xx == 0:
        return None, None, None

    a = ss_xy / ss_xx
    b = mean_y - a * mean_x
    r_sq = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 0 else 0.0

    return a, b, r_sq


def load_existing_calib() -> dict:
    try:
        with open(PUMP_CALIB_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_calib(data: dict):
    with open(PUMP_CALIB_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  💾 Da luu → {PUMP_CALIB_FILE}")


# ══════════════════════════════════════════════════════════════════════════════
# CALIBRATION MỘT BƠM
# ══════════════════════════════════════════════════════════════════════════════

def calibrate_one_pump(pump_number: int, window: collections.deque) -> dict | None:
    """
    Hiệu chuẩn một bơm qua nhiều mốc target dồn tích.

    Quy trình:
        - Bơm liên tục từ 0 → 100g → 200g → 300g → 400g (không đổ đi giữa chừng)
        - Mỗi khi đạt mốc: ghi (tổng thời gian, gram thực tế sau ổn định)
        - Linear regression trên toàn bộ dữ liệu

    Returns dict với gram_per_sec, dead_gram, r_squared, points
    """
    if pump_number not in PUMP_GPIO:
        print(f"  Bom {pump_number} khong hop le.")
        return None

    gpio_pin = PUMP_GPIO[pump_number]

    print(f"\n{'═' * 55}")
    print(f"  HIEU CHUAN BOM #{pump_number}  (GPIO {gpio_pin})")
    print(f"{'═' * 55}")
    print(f"  Se do tai {len(CALIB_TARGETS_GRAM)} moc: {CALIB_TARGETS_GRAM} gram")
    print(f"  Ly can chua duoc it nhat {CALIB_TARGETS_GRAM[-1] + 50}ml\n")

    # ── Đặt ly + tare ─────────────────────────────────────────────────────
    print(f"  [1] Dat ly RONG len can, dat voi bom #{pump_number} vao ly.")
    input("      → Nhan Enter khi san sang...")

    print("      Dang tru bi ly...", end=" ", flush=True)
    tare(30)
    clear_buffer(window)
    print("xong!")

    w0 = read_stable_weight(window)
    print(f"      Kiem tra zero: {w0:+.2f} g")

    # ── Bơm liên tục qua từng mốc ─────────────────────────────────────────
    pwm = PWMLED(gpio_pin, frequency=1000)
    data_points = []   # [(thoi_gian_giay, gram_thuc_te), ...]
    t_total = 0.0      # Tổng thời gian đã bơm (cộng dồn qua các mốc)

    print(f"\n  [2] Bat dau bom qua {len(CALIB_TARGETS_GRAM)} moc...\n")

    try:
        for idx, target_gram in enumerate(CALIB_TARGETS_GRAM):
            print(f"  ── Moc {idx + 1}/{len(CALIB_TARGETS_GRAM)}: target = {target_gram} g ──")

            clear_buffer(window)
            stop_target = target_gram - EARLY_STOP_GRAM

            pwm.value = 1.0
            t_seg_start = time.monotonic()

            # Closed-loop: đọc cân liên tục, tắt khi gần đến target
            while True:
                gram = read_weight_robust(window)
                if gram is None:
                    continue

                elapsed_seg = time.monotonic() - t_seg_start
                display = 0.0 if abs(gram) < 1.0 else gram
                bar = "█" * min(int(display / 10), 40)
                print(
                    f"\r    +{elapsed_seg:5.2f}s  {display:7.2f}/{target_gram} g  [{bar:<40}]",
                    end="", flush=True
                )

                if gram >= stop_target:
                    pwm.value = 0.0
                    t_seg_stop = time.monotonic()
                    break

                sleep(0.03)

            print()

            # Cộng dồn thời gian bơm
            t_total += (t_seg_stop - t_seg_start)

            # Chờ nước ổn định
            print(f"    Cho nuoc on dinh...", end=" ", flush=True)
            sleep(2)

            final_gram = read_stable_weight(window)
            print(f"xong!  Cuoi: {final_gram:.2f} g  |  Tong t bom: {t_total:.3f}s")

            if final_gram is None or final_gram < 10:
                print(f"  ⚠️  Ket qua bat thuong ({final_gram} g). Bo qua moc nay.")
                continue

            data_points.append((t_total, final_gram))
            print()

    except Exception as e:
        pwm.value = 0.0
        print(f"\n  Loi: {e}")
        raise
    finally:
        pwm.off()

    if len(data_points) < 2:
        print("  Khong du du lieu de tinh regression (can it nhat 2 moc).")
        return None

    # ── Linear regression ─────────────────────────────────────────────────
    times = [p[0] for p in data_points]
    grams = [p[1] for p in data_points]
    a, b, r_sq = linear_regression(times, grams)

    if a is None or a <= 0:
        print("  Regression that bai. Du lieu co the bi loi.")
        return None

    print(f"  ✅ HOI QUY TUYEN TINH:")
    print(f"     gram = {a:.4f} × giay + ({b:.4f})")
    print(f"     Toc do thuc  (a) = {a:.4f} g/s")
    print(f"     Dead zone    (b) = {b:.4f} g  ← tat bom som hon luong nay")
    print(f"     R²               = {r_sq:.6f}  (1.0 = hoan hao)")

    if r_sq < 0.995:
        print(f"\n  ⚠️  R² = {r_sq:.4f} < 0.995 — do chinh xac chua cao.")
        print(f"     Goi y: kiem tra voi bom co bi rung? nuoc co bi kep khi bom ngat?")

    # ── Bảng kiểm tra ─────────────────────────────────────────────────────
    print(f"\n  Bang kiem tra (du doan vs thuc te):")
    print(f"  {'Target':>8}  {'Thuc te':>10}  {'Du doan':>10}  {'Sai so':>8}")
    print(f"  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*8}")
    for i, (t_sec, g_real) in enumerate(data_points):
        g_pred = a * t_sec + b
        err = g_real - g_pred
        print(f"  {CALIB_TARGETS_GRAM[i]:>6}g  {g_real:>10.2f}  {g_pred:>10.2f}  {err:>+8.2f}")

    return {
        "gram_per_sec": round(a, 6),
        "dead_gram":    round(b, 6),
        "r_squared":    round(r_sq, 8),
        "points":       [(round(t, 4), round(g, 4)) for t, g in data_points],
    }


# ══════════════════════════════════════════════════════════════════════════════
# IN BẢNG TÓM TẮT
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(calib_data: dict):
    print("\n" + "═" * 70)
    print("  BANG TOM TAT HIEU CHUAN BOM")
    print("═" * 70)
    print(f"  {'Bom':<8} {'g/s':>8}  {'Dead(g)':>9}  {'R²':>10}  "
          f"{'100ml':>9}  {'250ml':>9}  {'500ml':>9}")
    print("  " + "─" * 66)
    for pump_id, d in sorted(calib_data.items()):
        a   = d["gram_per_sec"]
        b   = d["dead_gram"]
        r   = d["r_squared"]
        # Thời gian chạy bơm = (target_ml - dead_gram) / gram_per_sec
        t100 = max(0.0, (100 - b) / a) if a > 0 else 0
        t250 = max(0.0, (250 - b) / a) if a > 0 else 0
        t500 = max(0.0, (500 - b) / a) if a > 0 else 0
        print(f"  {pump_id:<8} {a:>8.3f}  {b:>9.3f}  {r:>10.6f}  "
              f"{t100:>8.2f}s  {t250:>8.2f}s  {t500:>8.2f}s")
    print("═" * 70)


# ══════════════════════════════════════════════════════════════════════════════
# CHƯƠNG TRÌNH CHÍNH
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  HIEU CHUAN BOM — CLOSED LOOP + REGRESSION")
    print("=" * 55)

    load_calibration(CALIBLOADCELL_FILE)
    window = collections.deque(maxlen=WINDOW_SIZE)

    pump_calib = load_existing_calib()
    if pump_calib:
        print(f"\n  Tim thay {len(pump_calib)} bom da hieu chuan truoc do.")
        print_summary(pump_calib)

    print("\n  Nhap danh sach so bom can hieu chuan (cach nhau bang dau phay).")
    print("  Vi du: 1,2,3  hoac  all  (ca 10 bom)")
    raw = input("  > ").strip().lower()

    if raw == "all":
        pump_numbers = list(PUMP_GPIO.keys())
    else:
        pump_numbers = []
        for token in raw.split(","):
            token = token.strip()
            if token.isdigit() and int(token) in PUMP_GPIO:
                pump_numbers.append(int(token))
            else:
                print(f"  Bo qua: '{token}' khong hop le.")

    if not pump_numbers:
        print("  Khong co bom nao. Thoat.")
        exit(0)

    print(f"\n  Se hieu chuan {len(pump_numbers)} bom: {pump_numbers}")
    input("  → Nhan Enter de bat dau...")

    for pump_number in pump_numbers:
        try:
            result = calibrate_one_pump(pump_number, window)
            if result:
                pump_calib[f"pump_{pump_number}"] = result
                save_calib(pump_calib)
        except KeyboardInterrupt:
            print(f"\n  Ngat tai bom {pump_number}. Luu du lieu da co...")
            save_calib(pump_calib)
            break
        except Exception as e:
            print(f"\n  Loi bom {pump_number}: {e}")
            continue

        if pump_number != pump_numbers[-1]:
            print("\n  Luu y: Lam trong ly truoc khi hieu chuan bom tiep theo.")
            cont = input("  Tiep tuc? (Enter = co / n = dung): ").strip().lower()
            if cont == "n":
                break

    print_summary(pump_calib)

    print("""
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CACH SU DUNG TRONG CODE THUC TE (closed-loop bang loadcell):

      import json, collections
      from gpiozero import PWMLED
      from loadcell import read_weight_robust, WINDOW_SIZE

      with open("pump_calib.json") as f:
          pump_calib = json.load(f)

      def pump_ml(pump_number: int, ml_target: float, window):
          d   = pump_calib[f"pump_{pump_number}"]
          a   = d["gram_per_sec"]
          b   = d["dead_gram"]
          # Tắt bơm sớm hơn dead_gram để bù lag nước trong ống
          stop_at = ml_target - b

          gpio = PUMP_GPIO[pump_number]
          pwm  = PWMLED(gpio, frequency=1000)
          pwm.value = 1.0
          while True:
              g = read_weight_robust(window)
              if g is not None and g >= stop_at:
                  pwm.off()
                  break
              sleep(0.03)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)
