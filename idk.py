"""
pump_ml_sequence.py
===================
Doc chuoi cac "step" bom tu file JSON va chay TUAN TU tung step.
Trong moi step, cac bom duoc chi dinh se chay SONG SONG voi nhau.

    step1     → bom 1 + bom 3   chay SONG SONG
                       ↓ xong xui moi sang
    step2     → bom 7 + bom 9   chay SONG SONG
                       ↓ xong xui moi sang
    step3     → bom 8 + bom 1   chay SONG SONG
                       ↓ xong xui moi sang
    step_cuoi → ca 10 bom        chay SONG SONG

Tinh nang chinh:
    ✓ Khong them thu vien moi — chi import lai pump_gram_multi_parallel
      tu pump_ml_parallel.py (giu nguyen json, threading, sleep, gpiozero).
    ✓ Doc cong thuc tu file JSON — de thay doi, khong can sua code.
    ✓ CHONG TRAN LY: kiem tra tong dung tich (gram → ml) cua TOAN BO
      chuoi step TRUOC khi bat bat ky bom nao. Neu vuot 500ml → huy ngay.

Cach dung doc lap:
    python pump_ml_sequence.py cong_thuc.json

Cach import vao file khac:
    from pump_ml_sequence import run_sequence_from_file
    from pump_ml_sequence import run_sequence

Dinh dang file JSON cong thuc:
    {
      "description":      "Ten cong thuc / ghi chu",   // tuy chon
      "density_g_per_ml": 1.0,                         // tuy chon, mac dinh 1.0
      "max_ml_per_cup":   500,                         // tuy chon, mac dinh 500
      "steps": [
        {"name": "step1",     "pumps": [[1, 80], [3, 80]]},
        {"name": "step2",     "pumps": [[7, 80], [9, 80]]},
        {"name": "step3",     "pumps": [[8, 50], [1, 50]]},
        {"name": "step_cuoi", "pumps": [[1,7],[2,7],[3,7],[4,7],[5,7],
                                        [6,7],[7,7],[8,7],[9,7],[10,7]]}
      ]
    }
    → "pumps": [[so_bom, so_gram], ...]
    → Cac cap [bom, gram] trong cung 1 step se chay SONG SONG.
    → Cac step chay TUAN TU (step truoc xong moi chay step tiep theo).
"""

import json
from configuration.configuration import PUMP_STEP_FILE

# ── IMPORT DUY NHAT: tai su dung ham tu pump_ml_parallel, khong viet lai ──
from pump_control.pump_ml_parallel import pump_gram_multi_parallel   # noqa: E402

# ── CAU HINH MAC DINH ─────────────────────────────────────────────────────────
DEFAULT_MAX_ML_PER_CUP   = 500.0   # ml — gioi han chong tran ly
DEFAULT_DENSITY_G_PER_ML = 1.0     # g/ml — ty trong mac dinh (nuoc tinh khiet)
  

# ══════════════════════════════════════════════════════════════════════════════
# DOC VA KIEM TRA FILE JSON
# ══════════════════════════════════════════════════════════════════════════════

def _load_sequence_json(json_path: str) -> dict:
    """
    Doc va parse file JSON cong thuc.
    Raise ro rang neu file khong tim thay hoac JSON bi hong.
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Khong tim thay file cong thuc: '{json_path}'.\n"
            f"Hay kiem tra lai duong dan hoac tao file JSON theo mau."
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"File '{json_path}' khong phai JSON hop le: {exc}"
        )

    if "steps" not in data or not isinstance(data["steps"], list):
        raise ValueError(
            f"File '{json_path}' thieu truong 'steps' (list). "
            f"Xem lai dinh dang JSON."
        )
    if len(data["steps"]) == 0:
        raise ValueError(f"File '{json_path}': 'steps' rong, khong co gi de chay.")

    return data


def _validate_step(step: dict, step_idx: int) -> list[tuple[int, float]]:
    """
    Kiem tra dinh dang mot step va tra ve danh sach [(pump_number, gram_target)].
    Raise ValueError neu co loi.
    """
    name = step.get("name", f"step_{step_idx + 1}")

    if "pumps" not in step or not isinstance(step["pumps"], list):
        raise ValueError(
            f"Step '{name}' (index {step_idx}) thieu truong 'pumps' (list)."
        )
    if len(step["pumps"]) == 0:
        raise ValueError(
            f"Step '{name}' (index {step_idx}) co 'pumps' rong."
        )

    orders = []
    for i, item in enumerate(step["pumps"]):
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            raise ValueError(
                f"Step '{name}', phan tu [{i}]: can dinh dang [so_bom, so_gram], "
                f"nhung nhan duoc: {item!r}"
            )
        try:
            pump_number = int(item[0])
            gram_target = float(item[1])
        except (ValueError, TypeError):
            raise ValueError(
                f"Step '{name}', phan tu [{i}]: "
                f"so_bom phai la so nguyen, so_gram phai la so thuc. "
                f"Gia tri: {item!r}"
            )
        if pump_number < 1 or pump_number > 10:
            raise ValueError(
                f"Step '{name}', phan tu [{i}]: "
                f"so bom phai tu 1 den 10, nhan duoc: {pump_number}"
            )
        if gram_target <= 0:
            raise ValueError(
                f"Step '{name}', bom #{pump_number}: "
                f"so_gram phai > 0, nhan duoc: {gram_target}"
            )
        orders.append((pump_number, gram_target))

    return orders


# ══════════════════════════════════════════════════════════════════════════════
# KIEM TRA CHONG TRAN LY (TRUOC KHI BOM)
# ══════════════════════════════════════════════════════════════════════════════

def _tinh_tong_ml(
    all_orders: list[list[tuple[int, float]]],
    density_g_per_ml: float,
) -> float:
    """
    Cong don tong so ml se bom qua TOAN BO cac step (1 ly duy nhat).
    Cong thuc: ml = (tong_gram) / density_g_per_ml
    """
    tong_gram = sum(gram for orders in all_orders for _, gram in orders)
    return tong_gram / density_g_per_ml


def _check_overflow(
    all_orders: list[list[tuple[int, float]]],
    density_g_per_ml: float,
    max_ml_per_cup: float,
    verbose: bool = True,
) -> float:
    """
    Kiem tra tong dung tich truoc khi bat bat ky bom nao.
    Neu vuot max_ml_per_cup → raise ValueError, KHONG bom bat ky giot nao.
    Tra ve tong ml neu hop le.
    """
    tong_ml = _tinh_tong_ml(all_orders, density_g_per_ml)

    if tong_ml > max_ml_per_cup:
        raise ValueError(
            f"\n"
            f"  ╔══ CANH BAO: CHONG TRAN LY ══════════════════════════════╗\n"
            f"  ║  Tong dung tich yeu cau : {tong_ml:>8.1f} ml              ║\n"
            f"  ║  Gioi han cho phep      : {max_ml_per_cup:>8.1f} ml              ║\n"
            f"  ║  Vuot qua               : {tong_ml - max_ml_per_cup:>8.1f} ml              ║\n"
            f"  ║                                                          ║\n"
            f"  ║  Toan bo lenh bom da bi HUY.                            ║\n"
            f"  ║  Khong co bom nao duoc kich hoat.                       ║\n"
            f"  ╚══════════════════════════════════════════════════════════╝"
        )

    if verbose:
        phan_tram = (tong_ml / max_ml_per_cup) * 100
        print(f"  [KIEM TRA] Tong du kien: {tong_ml:.1f}ml / {max_ml_per_cup:.0f}ml "
              f"({phan_tram:.1f}%) — OK, tien hanh bom.")

    return tong_ml


# ══════════════════════════════════════════════════════════════════════════════
# CHAY MOT STEP (song song) — goi truc tiep pump_gram_multi_parallel
# ══════════════════════════════════════════════════════════════════════════════

def run_step(
    name: str,
    orders: list[tuple[int, float]],
    step_idx: int,
    total_steps: int,
    verbose: bool = True,
) -> dict[int, float]:
    """
    Chay MOT step: tat ca bom trong 'orders' khoi dong CUNG MOT LUC.
    Ham nay chi tro ve sau khi BOM CUOI CUNG trong step hoan thanh.

    Tham so:
        name        — ten step (vi du: "step1", "step_cuoi")
        orders      — [(pump_number, gram_target), ...]
        step_idx    — thu tu step (bat dau tu 0), dung de in tien do
        total_steps — tong so step, dung de in tien do
        verbose     — True = in log, False = im lang

    Tra ve:
        dict { pump_number: duration_giay }
        (neu bom nao loi, gia tri la Exception thay vi float)
    """
    if verbose:
        sep = "═" * 60
        print(f"\n{sep}")
        print(f"  [{step_idx + 1}/{total_steps}] {name.upper()}")
        pump_info = " + ".join(f"bom#{p}={g:.0f}g" for p, g in orders)
        print(f"  Chay song song: {pump_info}")
        print(sep)

    results = pump_gram_multi_parallel(orders, verbose=verbose)

    if verbose:
        loi = {p: v for p, v in results.items() if isinstance(v, Exception)}
        ok  = {p: v for p, v in results.items() if not isinstance(v, Exception)}
        if loi:
            for p, e in loi.items():
                print(f"  [{name}] Bom #{p} LOI: {e}")
        if ok:
            print(f"  [{name}] Hoan thanh: "
                  + ", ".join(f"bom#{p}={v:.3f}s" for p, v in ok.items()))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# CHAY TOAN BO CHUOI (tuan tu step, song song trong step)
# ══════════════════════════════════════════════════════════════════════════════

def run_sequence(
    steps: list[dict],
    density_g_per_ml: float = DEFAULT_DENSITY_G_PER_ML,
    max_ml_per_cup: float   = DEFAULT_MAX_ML_PER_CUP,
    verbose: bool           = True,
) -> list[dict]:
    """
    Chay TOAN BO chuoi step TUAN TU.
    Trong moi step, cac bom chay SONG SONG voi nhau.

    Quy trinh:
        1. Kiem tra tat ca step, validate du lieu.
        2. Tinh tong dung tich (ml) cua CA CHUOI.
        3. Neu tong > max_ml_per_cup → DUNG NGAY, khong bom gi ca.
        4. Neu OK → chay tung step theo thu tu, doi step truoc xong
           moi chay step tiep theo.

    Tham so:
        steps            — list dict tung step tu JSON
        density_g_per_ml — ty trong chat long (g/ml), mac dinh 1.0 (nuoc)
        max_ml_per_cup   — gioi han tong dung tich cho 1 ly (ml)
        verbose          — in log ra man hinh

    Tra ve:
        list[dict] — ket qua tung step:
            [
              {"name": "step1", "orders": [(1,80),(3,80)], "results": {1:8.30, 3:8.39}},
              ...
            ]
    """
    if verbose:
        print(f"\n{'═' * 60}")
        print(f"  CHUOI BOM: {len(steps)} STEP")
        print(f"  Ty trong: {density_g_per_ml} g/ml | Gioi han ly: {max_ml_per_cup:.0f} ml")
        print(f"{'═' * 60}")

    # ── Buoc 1: kiem tra tat ca step truoc ──────────────────────────────────
    all_orders: list[list[tuple[int, float]]] = []
    for i, step in enumerate(steps):
        orders = _validate_step(step, i)
        all_orders.append(orders)

    # ── Buoc 2 & 3: kiem tra chong tran ly TRUOC khi bat bom nao ────────────
    _check_overflow(all_orders, density_g_per_ml, max_ml_per_cup, verbose=verbose)

    # ── Buoc 4: chay tung step tuan tu ──────────────────────────────────────
    all_results = []
    total = len(steps)

    for i, (step, orders) in enumerate(zip(steps, all_orders)):
        name = step.get("name", f"step_{i + 1}")
        results = run_step(name, orders, step_idx=i, total_steps=total, verbose=verbose)
        all_results.append({
            "name":    name,
            "orders":  orders,
            "results": results,
        })

    if verbose:
        print(f"\n{'═' * 60}")
        print(f"  HOAN THANH TOAN BO {total} STEP.")
        print(f"  Tom tat:")
        for r in all_results:
            n = r["name"]
            for p, g in r["orders"]:
                val = r["results"].get(p)
                if isinstance(val, Exception):
                    print(f"    {n} | bom#{p}: LOI — {val}")
                else:
                    print(f"    {n} | bom#{p}: {g:.0f}g da bom trong {val:.3f}s")
        print(f"{'═' * 60}")

    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# HAM TIEN ICH: DOC FILE JSON VA CHAY
# ══════════════════════════════════════════════════════════════════════════════

def run_sequence_from_file(json_path: str, verbose: bool = True) -> list[dict]:
    """
    Doc file JSON cong thuc va chay toan bo chuoi step.

    Vi du:
        run_sequence_from_file("pump_sequence_example.json")

    Dinh dang file JSON can thiet (xem pump_sequence_example.json de tham khao):
        {
          "description":      "...",     // tuy chon
          "density_g_per_ml": 1.0,       // tuy chon, mac dinh 1.0
          "max_ml_per_cup":   500,       // tuy chon, mac dinh 500
          "steps": [
            {"name": "step1",     "pumps": [[1, 80], [3, 80]]},
            {"name": "step2",     "pumps": [[7, 80], [9, 80]]},
            {"name": "step3",     "pumps": [[8, 50], [1, 50]]},
            {"name": "step_cuoi", "pumps": [[1,7],[2,7],...,[10,7]]}
          ]
        }
    """
    data = _load_sequence_json(json_path)

    steps       = data["steps"]
    density     = float(data.get("density_g_per_ml", DEFAULT_DENSITY_G_PER_ML))
    max_ml      = float(data.get("max_ml_per_cup",   DEFAULT_MAX_ML_PER_CUP))
    description = data.get("description", "")

    if verbose:
        print(f"\n  File     : '{json_path}'")
        if description:
            print(f"  Cong thuc: {description}")
        print(f"  Ty trong : {density} g/ml | Gioi han ly: {max_ml:.0f} ml | So step: {len(steps)}")

    return run_sequence(
        steps,
        density_g_per_ml = density,
        max_ml_per_cup   = max_ml,
        verbose          = verbose,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CHAY THU TRUC TIEP: python pump_ml_sequence.py <file.json>
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  PUMP ML SEQUENCE")
    print("  Chuoi step TUAN TU — Trong step chay SONG SONG")
    print("  Chong tran ly: mac dinh 500 ml/ly")
    print("=" * 60)

    # Neu khong truyen argument → tu dong dung PUMP_STEP_FILE mac dinh
json_path = sys.argv[1] if len(sys.argv) >= 2 else PUMP_STEP_FILE

    try:
        run_sequence_from_file(sys.argv[1], verbose=True)
    except (ValueError, FileNotFoundError) as exc:
        print(f"\n{exc}")
        sys.exit(1)
