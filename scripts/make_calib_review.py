"""Draw checkerboard corners and a contact sheet for a calibration image folder."""
from pathlib import Path
import argparse
import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=9)
    args = ap.parse_args()
    base = args.dir
    images = sorted(list((base / "images").glob("*.jpg")) + list((base / "images").glob("*.jpeg")) + list((base / "images").glob("*.png")))
    review = base / "review"
    review.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for f in images:
        img = cv2.imdecode(np.fromfile(str(f), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            print("skip unreadable", f)
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ok, corners = cv2.findChessboardCorners(
            gray, (args.cols, args.rows),
            cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ok:
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
                                       (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
            cv2.drawChessboardCorners(img, (args.cols, args.rows), corners, ok)
        out = review / (f.stem + "_corners.jpg")
        ok_enc, buf = cv2.imencode(".jpg", img)
        if ok_enc:
            out.write_bytes(buf.tobytes())
        h, w = img.shape[:2]
        thumbs.append(cv2.resize(img, (420, int(h * 420 / w))))
        print(("OK  " if ok else "FAIL") + " " + f.name)
    if thumbs:
        rows = []
        for i in range(0, len(thumbs), 5):
            row = thumbs[i:i + 5]
            while len(row) < 5:
                row.append(np.full_like(thumbs[0], 255))
            rows.append(np.hstack(row))
        sheet = np.vstack(rows)
        out = review / "contact_sheet.jpg"
        ok_enc, buf = cv2.imencode(".jpg", sheet)
        if ok_enc:
            out.write_bytes(buf.tobytes())
        print("wrote", out)


if __name__ == "__main__":
    main()
