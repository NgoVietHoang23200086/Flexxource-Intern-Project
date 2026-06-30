"""
init_loadcell.py
=============
Chạy MỘT LẦN DUY NHẤT để hiệu chuẩn cân với quả cân mẫu 83.3g.
Kết quả lưu vào calib.json — các lần sau không cần chạy lại.

Cách dùng:
    python init_loadcell.py
"""

import json
import time
from gpiozero import OutputDevice, DigitalInputDevice
from configuration.configuration import CALIBLOADCELL_FILE

# ── PIN ───────────────────────────────────────────────────────────────────────
SCK_PIN       = 4
DT_PIN        = 18
KNOWN_WEIGHT  = 83.3   # gram — quả cân mẫu
SAMPLES       = 50     # Càng nhiều mẫu càng chính xác

# ── PHẦN CỨNG ─────────────────────────────────────────────────────────────────
sck = OutputDevice(SCK_PIN)
dt  = DigitalInputDevice(DT_PIN)
sck.off()


def _read_raw(timeout_ms: int = 500) -> float | None:
    deadline = time.monotonic() + timeout_ms / 1000
    while dt.value == 1:
        if time.monotonic() > deadline:
            return None
        time.sleep(0.0001)
    count = 0
    for _ in range(24):
        sck.on()
        count = (count << 1) | (1 if dt.value else 0)
        sck.off()
    sck.on()
    sck.off()
    if count & 0x800000:
        count -= 0x1000000
    return float(count)


def _average(n: int) -> float:
    buf = []
    fails = 0
    while len(buf) < n:
        v = _read_raw()
        if v is not None:
            buf.append(v)
        else:
            fails += 1
            if fails > n * 3:
                raise RuntimeError("HX711 không phản hồi — kiểm tra kết nối.")
    return sum(buf) / len(buf)


def main():
    print("=" * 45)
    print("   HIỆU CHUẨN CÂN — CHẠY 1 LẦN DUY NHẤT")
    print("=" * 45)

    # BƯỚC 1 — Tare bàn cân trống
    print("\n[BƯỚC 1] Đảm bảo bàn cân TRỐNG hoàn toàn.")
    input("         → Nhấn Enter khi sẵn sàng... ")
    print(f"         Đang lấy {SAMPLES} mẫu offset...", end=" ", flush=True)
    offset = _average(SAMPLES)
    print(f"xong.  RAW offset = {offset:.1f}")

    # BƯỚC 2 — Đặt quả cân mẫu
    print(f"\n[BƯỚC 2] Đặt quả cân mẫu {KNOWN_WEIGHT}g lên bàn cân.")
    input("         → Nhấn Enter khi sẵn sàng... ")
    print(f"         Đang lấy {SAMPLES} mẫu với quả cân...", end=" ", flush=True)
    raw_with = _average(SAMPLES)
    print(f"xong.  RAW với cân = {raw_with:.1f}")

    # BƯỚC 3 — Tính SCALE
    scale = (raw_with - offset) / KNOWN_WEIGHT
    if abs(scale) < 1:
        print("\n❌ SCALE quá nhỏ — có thể cân không được kết nối đúng.")
        return

    # BƯỚC 4 — Kiểm tra nhanh
    check = (raw_with - offset) / scale
    print(f"\n✅ Kiểm tra: {check:.2f}g (kỳ vọng {KNOWN_WEIGHT}g) "
          f"— sai số {abs(check - KNOWN_WEIGHT):.2f}g")

    # BƯỚC 5 — Lưu file
    with open(CALIBLOADCELL_FILE, "w") as f:
        json.dump({"offset": offset, "scale": scale}, f, indent=2)

    print(f"\n💾 Đã lưu → {CALIBLOADCELL_FILE}")
    print(f"   OFFSET = {offset:.2f}")
    print(f"   SCALE  = {scale:.6f}")
    print("\n✅ Hiệu chuẩn hoàn tất.\n")


if __name__ == "__main__":
    main()
