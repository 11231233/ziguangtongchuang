"""Grab one frame from the HDMI capture card and save it as PNG.

The calibration console cannot be used for this: it decodes the four-page capture tags,
and the runtime firmware emits no tags. This grabs the card directly, with the same
resolution request the console uses, so a RAW/COR pair differs only by the KEY0 state.

    python grab_frame.py --device 0 --out raw_center.png
    python grab_frame.py --device 0 --out cor_center.png --preview
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

# Must be set before cv2 is imported: the probe opens indices that have no device and
# OpenCV would print a WARN for each, burying the useful lines.
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")

import cv2
import numpy as np


def list_devices(max_index: int = 6, preview_dir: Path | None = None) -> int:
    """Probe capture devices 0..max_index-1 and save a preview of each working one.

    Resolution alone cannot tell the capture card from the laptop webcam: both can report
    1280x720. A preview image is the only reliable way for a human to pick the right index.
    """
    # OpenCV prints a WARN for every index that has no device; that noise hides the
    # useful output.
    try:
        cv2.setLogLevel(0)          # LOG_LEVEL_SILENT
    except AttributeError:
        pass
    preview_dir = preview_dir or (Path.cwd() / "device_previews")
    preview_dir.mkdir(parents=True, exist_ok=True)
    print(f"探测采集卡设备号（每个试 12 帧）...  预览图写到 {preview_dir}")
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        frame = None
        for _ in range(12):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
        cap.release()
        if frame is None:
            print(f"  设备 {idx}: 能打开但取不到帧（可能被别的程序占用）")
            continue
        h, w = frame.shape[:2]
        p = preview_dir / f"device_{idx}.png"
        ok, buf = cv2.imencode(".png", cv2.resize(frame, (w // 3, h // 3),
                                                  interpolation=cv2.INTER_AREA))
        if ok:
            p.write_bytes(buf.tobytes())
        found.append((idx, (w, h), p))
        print(f"  设备 {idx}: 可用, 返回 {w}x{h}   预览 {p}")
    if not found:
        print("\n没有可用的采集设备。确认 HDMI 已接、板子已上电、采集软件已关闭。")
        return 1
    print("\n打开上面的预览图，认出哪一张是板子的 HDMI 输出（带 SRC/OUT/CALC 那几行字），")
    print("那个设备号就是要用的 --device。摄像头会在预览里显示房间画面。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", type=int, default=0, help="capture card index, not a COM port")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--frames", type=int, default=40, help="frames to discard before saving")
    ap.add_argument("--pick", choices=("last", "sharpest"), default="last")
    ap.add_argument("--preview", action="store_true", help="also write <out>_preview.png downscaled")
    ap.add_argument("--rotate", choices=("none", "cw", "ccw", "180", "vflip", "hflip"), default="none",
                    help="some UVC cards hand OpenCV a frame rotated 90 degrees; pick the "
                         "one that makes the OSD text sit horizontally in the top-left")
    ap.add_argument("--list", action="store_true", help="probe device indices and exit")
    ap.add_argument("--preview-dir", type=Path, help="where --list writes device previews")
    a = ap.parse_args(argv)

    if a.list:
        return list_devices(preview_dir=a.preview_dir)
    if a.out is None:
        raise SystemExit("--out required (or use --list)")

    cap = cv2.VideoCapture(a.device, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(
            f"打不开设备 {a.device}。最常见原因是标定控制台或采集软件还开着并占用了采集卡，"
            f"先全部关掉再试；也用 --list 确认设备号。")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    best, best_score = None, -1.0
    for _ in range(max(1, a.frames)):
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        if a.pick == "sharpest":
            score = float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
            if score > best_score:
                best, best_score = frame, score
        else:
            best = frame
    cap.release()

    if best is None:
        raise SystemExit("no frame captured; check the card is not held by another program")
    if a.rotate != "none":
        # The capture card on this bench hands OpenCV a vertically flipped frame: the OSD
        # block lands bottom-left and only becomes readable after --rotate vflip.
        best = {
            "vflip": lambda f: cv2.flip(f, 0),
            "hflip": lambda f: cv2.flip(f, 1),
            "cw": lambda f: cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE),
            "ccw": lambda f: cv2.rotate(f, cv2.ROTATE_90_COUNTERCLOCKWISE),
            "180": lambda f: cv2.rotate(f, cv2.ROTATE_180),
        }[a.rotate](best)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", best)
    if not ok:
        raise SystemExit("PNG encode failed")
    a.out.write_bytes(buf.tobytes())
    h, w = best.shape[:2]
    print(f"saved {a.out}   {w}x{h}" + (f"   sharpness={best_score:.0f}" if a.pick == "sharpest" else ""))
    if a.rotate != "none":
        print(f"已做 {a.rotate} 旋转；请确认 OSD 那几行字是水平的且在左上角")
    if not ((w, h) == (1280, 720) or (w, h) == (720, 1280)):
        print(f"WARNING: expected 1280x720 from the runtime firmware, got {w}x{h}")
    if a.preview:
        prev = cv2.resize(best, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", prev)
        if ok:
            p = a.out.with_name(a.out.stem + "_preview.png")
            p.write_bytes(buf.tobytes())
            print(f"preview {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())