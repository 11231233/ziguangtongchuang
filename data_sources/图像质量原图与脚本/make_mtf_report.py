"""生成 RAW/COR 的 MTF 对比图和 JSON 汇总。"""
import json
import statistics as st
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pair_mtf import measure

RAW = Path(r"F:\ziguang_jibian\A_first.png")
COR = Path(r"F:\ziguang_jibian\B_second.png")
OUT = Path(r"F:\ziguang_jibian\mtf")


def main():
    R = measure(RAW, "6x9", 40)
    C = measure(COR, "6x9", 40)
    mr, mc = st.median(R["mtf50"]), st.median(C["mtf50"])
    nr, nc = st.median(R["per_square"]), st.median(C["per_square"])

    print(f"RAW 中位 {mr:.4f}  每格 {nr:.3f}  样本 {R['good']}/{R['rois']}  格子 {R['square']:.2f} px")
    print(f"COR 中位 {mc:.4f}  每格 {nc:.3f}  样本 {C['good']}/{C['rois']}  格子 {C['square']:.2f} px")
    print(f"变化   归一化 {(nc-nr)/nr*100:+.2f}%   未归一化 {(mc-mr)/mr*100:+.2f}%")

    W, H = 760, 420
    img = np.full((H, W, 3), 255, np.uint8)
    bins = np.linspace(0.12, 0.32, 21)

    def panel(vals, x0, label, color, med, n):
        h, _ = np.histogram(vals, bins)
        bw = (W // 2 - 60) / len(h)
        for i, c in enumerate(h):
            bh = int(c / max(h.max(), 1) * 210)
            cv2.rectangle(img, (int(x0 + i * bw), 345 - bh),
                          (int(x0 + (i + 1) * bw - 2), 345), color, -1)
        cv2.putText(img, f"{label}  n={n}", (int(x0), 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        cv2.putText(img, f"median {med:.3f}", (int(x0), 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

    panel(R["mtf50"], 40, "RAW", (180, 120, 60), mr, R["good"])
    panel(C["mtf50"], W // 2 + 20, "COR", (60, 120, 190), mc, C["good"])
    cv2.line(img, (0, 345), (W, 345), (0, 0, 0), 1)
    for i in range(5):
        v = 0.12 + i * 0.05
        x = int(40 + (v - 0.12) / 0.20 * (W // 2 - 60))
        cv2.putText(img, f"{v:.2f}", (x, 365), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    cv2.putText(img, "MTF50 cycles/pixel", (W // 2 - 90, 398),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / "MTF_compare2.png"), img)

    payload = dict(
        pair=dict(raw=str(RAW), cor=str(COR)),
        control=dict(corner_shift_px=0.49, square_diff_px=0.20, tilt_diff_deg=0.10),
        raw=dict(median=mr, per_square=nr, square_px=R["square"],
                 samples=R["good"], candidates=R["rois"], values=R["mtf50"]),
        cor=dict(median=mc, per_square=nc, square_px=C["square"],
                 samples=C["good"], candidates=C["rois"], values=C["mtf50"]),
        normalized_change_pct=(nc - nr) / nr * 100,
        unnormalized_change_pct=(mc - mr) / mr * 100,
    )
    (OUT / "pair_result_v2.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"图 {OUT / 'MTF_compare2.png'}")
    print(f"表 {OUT / 'pair_result_v2.json'}")


if __name__ == "__main__":
    main()