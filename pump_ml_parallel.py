"""
pump_ml_parallel.py
===================
Bơm đúng số gram mong muốn chỉ dùng thông số calib — KHÔNG cần loadcell.
Phiên bản SONG SONG: tất cả các bơm trong lệnh chạy CÙNG LÚC.

Công thức:
    t = (gram_target - b) / a
    → Chạy bơm đúng t giây rồi tắt.

Cách dùng độc lập:
    python pump_ml_parallel.py

Cách import vào file khác:
    from pump_ml_parallel import pump_gram, pump_gram_multi_parallel

So sánh với pump_ml.py (tuần tự):
    pump_gram_multi([...])           → Bơm 1 xong → Bơm 2 xong → ...
    pump_gram_multi_parallel([...])  → Bơm 1 + Bơm 2 + ... chạy CÙNG LÚC
"""

import json
import threading
from time import sleep

from gpiozero import PWMLED

from configuration.configuration import PUMP_CALIB_FILE

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
# HÀM CHÍNH: BƠM MỘT BƠM (giữ nguyên từ pump_ml.py)
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
# HÀM MỚI: BƠM NHIỀU BƠM SONG SONG (tất cả cùng lúc)
# ══════════════════════════════════════════════════════════════════════════════

def pump_gram_multi_parallel(
    orders: list[tuple[int, float]],
    verbose: bool = True,
) -> dict[int, float | Exception]:
    """
    Bơm nhiều bơm SONG SONG — tất cả khởi động CÙNG MỘT LÚC.
    Hàm chỉ trả về sau khi BƠM CUỐI CÙNG hoàn thành.

    Tham số:
        orders  — danh sách [(pump_number, gram_target), ...]
                  ví dụ: [(1, 150.0), (10, 100.0)]
        verbose — in log hay không

    Trả về:
        dict — { pump_number: duration_giây } cho mỗi bơm
               Nếu bơm nào lỗi, giá trị là Exception thay vì float.

    Ví dụ:
        pump_gram_multi_parallel([(1, 100), (10, 150)])
        # Bơm #1 và Bơm #10 chạy ĐỒNG THỜI
        # Tổng thời gian ≈ max(t1, t10) thay vì t1 + t10
    """
    if not orders:
        return {}

    results: dict[int, float | Exception] = {}
    lock = threading.Lock()

    def _worker(pump_number: int, gram_target: float):
        try:
            duration = pump_gram(pump_number, gram_target, verbose=verbose)
            with lock:
                results[pump_number] = duration
        except Exception as e:
            with lock:
                results[pump_number] = e
            if verbose:
                print(f"  [Bom #{pump_number}] LOI: {e}")

    if verbose:
        pump_list = ", ".join(f"#{p} ({g:.1f}g)" for p, g in orders)
        print(f"\n  [SONG SONG] Khoi dong {len(orders)} bom cung luc: {pump_list}")

    # Tạo và khởi động tất cả thread cùng lúc
    threads = []
    for pump_number, gram_target in orders:
        t = threading.Thread(
            target=_worker,
            args=(pump_number, gram_target),
            daemon=True,
            name=f"pump-{pump_number}",
        )
        threads.append(t)

    # Kích hoạt tất cả thread gần như đồng thời
    for t in threads:
        t.start()

    # Chờ tất cả thread hoàn thành
    for t in threads:
        t.join()

    if verbose:
        print(f"\n  [SONG SONG] Tat ca {len(orders)} bom da hoan thanh.")
        for pump_number, gram_target in orders:
            val = results.get(pump_number)
            if isinstance(val, Exception):
                print(f"    Bom #{pump_number}: LOI — {val}")
            else:
                print(f"    Bom #{pump_number}: {gram_target:.1f}g xong trong {val:.3f}s")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# CHẠY THỬ TRỰC TIẾP
# ══════════════════════════════════════════════════════════════════════════════

# if __name__ == "__main__":
#     print("=" * 50)
#     print("  THU NGHIEM BOM SONG SONG")
#     print("=" * 50)

#     print("\n  Nhap lenh theo dinh dang:  <so_bom> <gram>")
#     print("  Vi du:  1 200             → Bom #1 bom 200g")
#     print("  Vi du:  1 100 10 150      → Bom #1 (100g) + Bom #10 (150g) CUNG LUC")
#     print("  Nhap 'q' de thoat.\n")

#     while True:
#         raw = input("  Lenh > ").strip().lower()
#         if raw == "q":
#             break

#         tokens = raw.split()
#         if len(tokens) < 2 or len(tokens) % 2 != 0:
#             print("  Sai dinh dang. Vi du: 1 200  hoac  1 100 10 150")
#             continue


#         orders = []
        
#         valid = True
#         for i in range(0, len(tokens), 2):
#             try:
#                 p = int(tokens[i])
#                 g = float(tokens[i + 1])
#                 orders.append((p, g))
#             except ValueError:
#                 print(f"  Gia tri khong hop le: '{tokens[i]}' '{tokens[i+1]}'")
#                 valid = False
#                 break

#         if not valid:
#             continue

#         pump_gram_multi_parallel(orders)

if __name__ == "__main__":
    print("=" * 50)
    print("   THU NGHIEM DOC KEY JSON & BOM SONG SONG")
    print("=" * 50)

    try:
        # 1. Đọc file JSON cấu hình trước một lần để lấy danh sách các Key (các Step)
        with open("configuration/pump_step.json", "r", encoding="utf-8") as f:
            steps_data = json.load(f)
        
        # Lấy tất cả các Key (mức ngoài cùng) chuyển thành một danh sách
        available_steps = list(steps_data.keys())
        
        print("  Các bước (Steps) tìm thấy trong file JSON:")
        for idx, step_name in enumerate(available_steps, 1):
            print(f"    {idx}. {step_name}")
        print("  --------------------------------------------------")
    except FileNotFoundError:
        print("  [LỖI] Không tìm thấy file cấu hình 'configuration/pump_step.json'.")
        available_steps = []
    except json.JSONDecodeError:
        print("  [LỖI] File JSON bị sai định dạng cú pháp.")
        available_steps = []

    # Vòng lặp điều khiển
    while available_steps:
        raw = input("  Nhập lựa chọn của bạn > ").strip()


        selected_step = None

        # Tình huống 1: Người dùng nhập số thứ tự (ví dụ: 1, 2)
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(available_steps):
                selected_step = available_steps[idx]
            else:
                print(f"  [LỖI] Số thứ tự không hợp lệ. Vui lòng nhập từ 1 đến {len(available_steps)}")
                continue
        # Tình huống 2: Người dùng nhập thẳng tên Key (ví dụ: step_1)
        else:
            if raw in steps_data:
                selected_step = raw
            else:
                print(f"  [LỖI] Không tìm thấy tên bước '{raw}' trong danh sách.")
                continue

        # Tiến hành xử lý dữ liệu của Key đã chọn
        print(f"  --> Đang kích hoạt: {selected_step}")
        try:
            orders = []
            # Truy cập vào mảng giá trị của Key được chọn (steps_data[selected_step])
            for item in steps_data[selected_step]:
                pump_num = int(item["pump"])
                gram_val = float(item["gram"])
                orders.append((pump_num, gram_val))

            # Chạy hàm song song
            pump_gram_multi_parallel(orders)

        except Exception as e:
            print(f"  [LỖI] Không thể thực thi cấu hình của {selected_step}: {e}")
