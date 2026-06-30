"""
loadcell_robust.py
==================
Drop-in replacement cho read_weight_smooth() trong loadcell.py.
Giải quyết vấn đề loadcell bị spike / nhiễu bậy giữa chừng.

Vấn đề gốc:
    Moving average (mean) với window=8 bị ảnh hưởng nặng bởi spike.
    Ví dụ: 100g bị spike lên 200g → trung bình lệch ~12g và kéo dài
    nhiều chu kỳ tiếp theo vì giá trị nhiễu vẫn nằm trong deque.

Giải pháp: Median + Spike Gate
    1. Đọc raw từ HX711 như bình thường
    2. Nếu raw mới lệch > SPIKE_THRESHOLD_GRAM so với median hiện tại
       → Bỏ qua raw này, trả về median hiện tại ngay
    3. Tính kết quả bằng median thay vì mean
       → Median hoàn toàn kháng spike đơn lẻ (< 50% window)

FIX QUAN TRỌNG so với v1:
    Import `loadcell.loadcell` là MODULE, không import OFFSET/SCALE trực tiếp.
    Nếu dùng `from loadcell.loadcell import OFFSET, SCALE` thì Python copy
    giá trị lúc import (0 và 1.0), load_calibration() sau đó không ảnh hưởng.
    Phải dùng `import loadcell.loadcell as _lc` rồi đọc `_lc.OFFSET`, `_lc.SCALE`
    để luôn lấy giá trị mới nhất sau khi load_calibration() chạy.

Cách dùng (thay thế read_weight_smooth):
    from loadcell_robust import read_weight_robust as read_weight_smooth

    window = collections.deque(maxlen=WINDOW_SIZE)
    gram = read_weight_smooth(window)
"""

import collections
import statistics

# ── IMPORT MODULE, KHÔNG IMPORT GIÁ TRỊ ────────────────────────────────────
# ĐÚNG:  import module → đọc _lc.OFFSET, _lc.SCALE mỗi lần gọi
#         → luôn lấy giá trị mới nhất sau load_calibration()
# SAI:   from loadcell.loadcell import OFFSET, SCALE
#         → copy giá trị lúc import (0, 1.0), không bao giờ cập nhật
import loadcell.loadcell as _lc

# Lấy WINDOW_SIZE (hằng số, không thay đổi sau load → ok import trực tiếp)
from loadcell.loadcell import WINDOW_SIZE

# ── CẤU HÌNH BỘ LỌC ─────────────────────────────────────────────────────────

# Ngưỡng spike: nếu gram mới lệch > giá trị này so với median hiện tại
# → coi là nhiễu, bỏ qua.
# Đặt đủ lớn để không lọc nhầm tín hiệu thật khi bơm đang chạy (~2-5g/chu kỳ)
# Đặt đủ nhỏ để bắt spike bậy (thường nhảy > 20-30g đột ngột)
SPIKE_THRESHOLD_GRAM = 15.0

# Số lần reject liên tiếp tối đa trước khi chấp nhận giá trị mới
# Tránh bị kẹt khi cân thật sự thay đổi nhanh (đổ nhiều nước cùng lúc)
MAX_CONSECUTIVE_REJECTS = 5

_consecutive_rejects = 0


def read_weight_robust(window: collections.deque) -> float | None:
    """
    Đọc loadcell với bộ lọc kháng spike.
    Drop-in replacement cho read_weight_smooth(window).

    Thuật toán:
        1. Đọc raw từ HX711
        2. Nếu window >= 4 mẫu: so raw mới với median hiện tại (gram)
           - Lệch > SPIKE_THRESHOLD_GRAM → bỏ qua, trả về median hiện tại
           - Reject > MAX_CONSECUTIVE_REJECTS lần liên tiếp → chấp nhận
             (tránh bị kẹt khi cân thật sự thay đổi nhanh)
        3. Thêm raw vào window, trả về median (thay vì mean)
    """
    global _consecutive_rejects

    raw = _lc.read_hx711()
    if raw is None:
        return None

    scale  = _lc.SCALE
    offset = _lc.OFFSET

    if scale == 0:
        return 0.0

    # Spike gate: cần đủ mẫu để tính ngưỡng có nghĩa
    if len(window) >= 4:
        current_median_raw = statistics.median(window)
        current_gram = (current_median_raw - offset) / scale
        new_gram     = (raw - offset) / scale
        delta        = abs(new_gram - current_gram)

        if delta > SPIKE_THRESHOLD_GRAM and _consecutive_rejects < MAX_CONSECUTIVE_REJECTS:
            _consecutive_rejects += 1
            return current_gram   # Trả về giá trị ổn định, bỏ qua spike
        else:
            _consecutive_rejects = 0
    else:
        _consecutive_rejects = 0

    # Thêm raw vào window và tính median
    window.append(raw)
    median_raw = statistics.median(window)
    return (median_raw - offset) / scale