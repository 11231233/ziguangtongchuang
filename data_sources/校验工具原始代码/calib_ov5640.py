#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calib_ov5640.py — 用棋盘格标定 OV5640 广角镜头，输出相机内参与畸变系数

用法：
    python tools/calib_ov5640.py --images calib/*.jpg --cols 9 --rows 6 --square 25

输出 calib_result.json：
    { "fx","fy","cx","cy","k1","k2","p1","p2",
      "rms", "image_size", "reprojection_error" }

随后用 warp_model.py 生成 RTL 系数：
    python tools/warp_model.py --calib calib_result.json --out-json coeff.json
"""
import argparse
import glob
import json
import os
import hashlib
from pathlib import Path

import cv2
import numpy as np
from checkerboard_detection import detect_checkerboard, CheckerboardNotFound


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True, help="棋盘格图片 glob，如 'calib/*.jpg'")
    ap.add_argument("--cols", type=int, default=9, help="内角点数（列）")
    ap.add_argument("--rows", type=int, default=6, help="内角点数（行）")
    ap.add_argument("--square", type=float, default=25.0, help="格子边长 mm")
    ap.add_argument("--out", default="calib_result.json")
    ap.add_argument("--min-views", type=int, default=10, help="minimum usable views; OpenCV needs 6, competition data should be >=10")
    ap.add_argument("--view-rms-warn", type=float, default=1.0, help="per-view reprojection RMS warning threshold (px)")
    ap.add_argument("--report", help="optional Markdown calibration report path")
    ap.add_argument('--source-kind', choices=['unverified', 'ov5640_raw_digital', 'phone_screen', 'synthetic', 'phone_direct', 'monitor_rectified'],
                    default='unverified', help='Capture provenance, declared by operator; not automatically authenticated')
    args = ap.parse_args()
    if min(args.cols, args.rows) < 3 or not np.isfinite(args.square) or args.square <= 0:
        ap.error('cols/rows must be at least 3 and square must be finite and positive')
    if args.source_kind == 'phone_screen':
        ap.error('手机拍屏混合了手机镜头和屏幕采样，不能直接用于OV5640真实内参标定；请使用直线度对照工具')
    if Path(args.out).exists():
        ap.error('输出已存在，请换新文件名以保留原始标定记录')

    pattern = (args.cols, args.rows)
    objp = np.zeros((args.cols * args.rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:args.cols, 0:args.rows].T.reshape(-1, 2) * args.square

    obj_points, img_points, used_files = [], [], []
    size = None
    seen_hashes, duplicate_files = set(), []
    input_hashes = {}
    indirect_meta = []
    files = sorted(glob.glob(args.images))
    if not files:
        raise SystemExit(f"没有匹配的图片: {args.images}")

    for f in files:
        # Windows OpenCV imread can fail on Chinese paths. Decode bytes instead.
        raw = Path(f).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if args.source_kind == 'monitor_rectified':
            sidecar = Path(f).parent / 'metadata.json'
            if not sidecar.is_file():
                raise SystemExit(f'缺少屏幕展开来源记录: {sidecar}')
            meta = json.loads(sidecar.read_text(encoding='utf-8'))
            snap = Path(f).parent / 'phone_calibration_snapshot.json'
            if not (meta.get('eligible_for_indirect_fit') and meta.get('output_sha256') == digest
                    and snap.is_file() and hashlib.sha256(snap.read_bytes()).hexdigest() == meta.get('phone_calibration_sha256')):
                raise SystemExit(f'间接取图记录不合格：需要手机模型、RAW/G0及匹配的图像哈希: {f}')
            phone_model = json.loads(snap.read_text(encoding='utf-8'))
            if phone_model.get('source_kind_operator_declared') != 'phone_direct':
                raise SystemExit('手机模型必须来自直接拍摄平面棋盘的phone_direct标定')
            if indirect_meta and meta['phone_calibration_sha256'] != indirect_meta[0]['phone_calibration_sha256']:
                raise SystemExit('同一间接标定集不能混用手机标定模型')
            indirect_meta.append(meta)
        if digest in seen_hashes:
            duplicate_files.append(f)
            print('跳过（重复图片，不能当作新角度）:', f)
            continue
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            print("跳过（读不了）:", f)
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        current_size = gray.shape[::-1]
        if args.source_kind in ('ov5640_raw_digital', 'monitor_rectified') and current_size != (1280, 720):
            raise SystemExit(f'本项目需要未缩放1280×720原始数字图像: {f}: {current_size}')
        if size is not None and current_size != size:
            raise SystemExit(f"图片尺寸不一致: {f}: {current_size}, 预期 {size}")
        try:
            corners = detect_checkerboard(img, pattern)['points'].reshape(-1, 1, 2)
        except CheckerboardNotFound:
            print("未找到角点:", f)
            continue
        obj_points.append(objp)
        img_points.append(corners)
        used_files.append(f)
        seen_hashes.add(digest)
        input_hashes[f] = digest
        size = current_size
        print("OK:", f)

    if len(obj_points) < max(6, args.min_views):
        raise SystemExit(f"有效图片只有 {len(obj_points)} 张，当前要求至少 {max(6, args.min_views)} 张不同角度；"
                         f"如确实只有较少图，可显式降低 --min-views，但不能低于 OpenCV 的 6 张")

    # Fit the exact four-coefficient model implemented by the FPGA. Fitting k3
    # and then silently dropping it gives a different camera model.
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, size, None, None, flags=cv2.CALIB_FIX_K3)
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    k1, k2, p1, p2, k3 = [float(x) for x in dist.ravel()[:5]]
    if not np.isfinite([rms, fx, fy, cx, cy, k1, k2, p1, p2]).all() or min(fx, fy) <= 0:
        raise SystemExit('标定解无效：需要更多清晰、不同角度的原始图像')
    view_errors=[]
    for name,obj,img,rv,tv in zip(used_files,obj_points,img_points,rvecs,tvecs):
        predicted,_=cv2.projectPoints(obj,rv,tv,K,dist)
        # OpenCV may return corners as (N,1,2) or (N,2); flatten both explicitly,
        # otherwise numpy broadcasts (N,1,2)-(N,2) to (N,N,2) and inflates the error.
        residual=predicted.reshape(-1,2)-img.reshape(-1,2)
        view_errors.append({'image':name,'rms_pixels':float(np.sqrt(np.mean(np.sum(residual**2,axis=1))))})
    view_rms=[v['rms_pixels'] for v in view_errors]
    max_view_rms=float(max(view_rms)) if view_rms else float('inf')
    outliers=[v for v in view_errors if v['rms_pixels']>args.view_rms_warn]
    w,h=size
    sanity={
        'focal_length_in_range': bool(0.15*w < fx < 12*w and 0.15*h < fy < 12*h),
        'principal_point_near_center': bool(abs(cx-w/2) < w/2 and abs(cy-h/2) < h/2),
        'distortion_coefficients_in_range': bool(abs(k1)<5 and abs(k2)<5 and abs(p1)<1 and abs(p2)<1),
        'view_rms_max_px': max_view_rms,
        'view_rms_warn_threshold_px': args.view_rms_warn,
        'views_over_threshold': [v['image'] for v in outliers],
    }
    if not sanity['focal_length_in_range']:
        raise SystemExit(f'标定焦距异常：fx={fx:.3f}, fy={fy:.3f}, image={size}；检查是否混入不同分辨率/裁切图')
    if not sanity['principal_point_near_center']:
        raise SystemExit(f'标定主点异常：cx={cx:.3f}, cy={cy:.3f}, image={size}；检查角点顺序与棋盘完整性')
    if not sanity['distortion_coefficients_in_range']:
        raise SystemExit(f'畸变系数异常：k1={k1:.4f}, k2={k2:.4f}, p1={p1:.4f}, p2={p2:.4f}；'
                         f'检查棋盘平整度、角点误检或视角覆盖')

    res = {
        "fx": fx, "fy": fy, "cx": cx, "cy": cy,
        "k1": k1, "k2": k2, "p1": p1, "p2": p2,
        "rms": float(rms),
        "image_size": list(size),
        "frames_used": len(obj_points),
        "checkerboard_inner_corners": [args.cols, args.rows],
        "square_size_mm_operator_declared": args.square,
        "square_size_physically_verified": False,
        "model": "opencv_k1_k2_p1_p2_k3_fixed_zero",
        "k3": k3,
        "duplicate_images_skipped": duplicate_files,
        "reprojection_error": view_errors,
        "max_view_rms_px": max_view_rms,
        "views_over_warn_threshold": sanity['views_over_threshold'],
        "sanity_checks": sanity,
        "min_views_required": max(6, args.min_views),
        "source_kind_operator_declared": args.source_kind,
        "capture_provenance_verified_by_tool": False,
        "synthetic_test_data": args.source_kind == 'synthetic' or any(m.get('synthetic_test_data') for m in indirect_meta),
        "input_images_sha256": input_hashes,
        "indirect_estimate": args.source_kind == 'monitor_rectified',
        "calibration_scope": 'phone_camera' if args.source_kind == 'phone_direct' else
            'ov5640_indirect_monitor_estimate' if args.source_kind == 'monitor_rectified' else 'source_declared_in_metadata',
        "high_precision_calibration_verified": False,
        "rectification_metadata": indirect_meta,
    }
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(res, fp, indent=2, ensure_ascii=False)

    if args.report:
        lines = [
            "# 标定报告",
            "",
            f"- 输入 glob：`{args.images}`",
            f"- 来源声明：`{args.source_kind}`（工具未认证，仅记录）",
            f"- 图像尺寸：`{size[0]}×{size[1]}`，有效帧：`{len(obj_points)}`",
            f"- 棋盘内角点：`{args.cols}×{args.rows}`，单格：`{args.square}` mm（操作者声明）",
            f"- 总重投影 RMS：`{rms:.4f}` px，逐图最大：`{max_view_rms:.4f}` px",
            f"- 模型：k1,k2,p1,p2，k3 固定 0",
            f"- 总耗时：{len(obj_points)} 张",
            "",
            "## 内参与畸变",
            "",
            "| fx | fy | cx | cy | k1 | k2 | p1 | p2 |",
            "|---|---|---|---|---|---|---|---|",
            f"| {fx:.3f} | {fy:.3f} | {cx:.3f} | {cy:.3f} | {k1:.6f} | {k2:.6f} | {p1:.6f} | {p2:.6f} |",
            "",
            "## 逐图重投影误差",
            "",
            "| 图像 | RMS (px) |",
            "|---|---|",
        ]
        for v in view_errors:
            lines.append(f"| `{Path(v['image']).name}` | {v['rms_pixels']:.4f} |")
        lines += [
            "",
            "## 检查",
            "",
            f"- 焦距范围：`{'PASS' if sanity['focal_length_in_range'] else 'FAIL'}`",
            f"- 主点范围：`{'PASS' if sanity['principal_point_near_center'] else 'FAIL'}`",
            f"- 畸变系数范围：`{'PASS' if sanity['distortion_coefficients_in_range'] else 'FAIL'}`",
            f"- 超过 {args.view_rms_warn}px 的视图：{', '.join('`'+Path(x).name+'`' for x in sanity['views_over_threshold']) or '无'}",
            "",
            "## 限制",
            "",
        ]
        if args.source_kind == "synthetic":
            lines.append("- 合成数据，仅用于工具自检，不能作为真实镜头标定。")
        elif args.source_kind == "phone_direct":
            lines.append("- 这是手机镜头内参，不是 OV5640 内参；只能用于第二阶段拍屏展开。")
        elif args.source_kind == "monitor_rectified":
            lines.append("- 这是手机拍屏展开后的间接估计，含手机模型、屏幕缩放、摩尔纹和手动四角误差；不能声明为 OV5640 原始像素高精度标定。")
        elif args.source_kind == "ov5640_raw_digital":
            lines.append("- 原始数字帧标定；仍需确认采集时分辨率、镜头、对焦、变焦未改变。")
        else:
            lines.append("- 图像来源未验证；不能作为比赛实测精度。")
        lines += [
            "- 低重投影 RMS 只说明角点拟合一致，不自动证明真实镜头精度；需要独立留出图或直线度/MTF 佐证。",
            "",
            "## 下一步",
            "",
        ]
        if args.source_kind == "phone_direct":
            lines += [
                "这是**手机镜头**内参，不是 OV5640 系数，**不要**用 `calib_to_fpga.py` 写入 FPGA。",
                "",
                "下一步：在图像质量工作台选择此 JSON 作为手机标定模型，展开开发板 RAW/G0/T0 屏幕照片，",
                "得到 `monitor_rectified` 后再做第二阶段间接标定。",
                "",
            ]
        elif args.source_kind == "synthetic":
            lines += [
                "这是合成数据，仅用于工具自检；不要写入比赛固件，也不要在报告中当作实测。",
                "",
            ]
        else:
            lines += [
                "```powershell",
                f"python tools/calib_to_fpga.py --calib \"{args.out}\" --out-dir calib_coeff_01"
                + (" --allow-indirect" if args.source_kind == "monitor_rectified" else "")
                + (" --allow-synthetic" if args.source_kind == "synthetic" else "")
                + (" --allow-unverified" if args.source_kind == "unverified" else "")
                + "```",
                "",
            ]
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text("\n".join(lines), encoding="utf-8")
        print("写入报告", args.report)

    print(f"\n标定完成：{len(obj_points)} 张，重投影 RMS = {rms:.4f} px")
    print(f"  fx={fx:.3f} fy={fy:.3f} cx={cx:.3f} cy={cy:.3f}")
    print(f"  k1={k1:.6f} k2={k2:.6f} p1={p1:.6f} p2={p2:.6f} (k3={k3:.6f} 未使用)")
    print("写入", args.out)
    if args.source_kind in ('unverified', 'synthetic'):
        print('图像来源未验证或为合成数据，本结果不能作为真实镜头标定验收。')
    if args.source_kind == 'monitor_rectified':
        print('这是手机模型与屏幕展开后的间接估计，不能作为原始数字取图的高精度标定验收。')
    if rms > 1.0:
        print("[!] RMS > 1px：检查棋盘是否平整、角点是否对准、是否用了不同焦距的图")


if __name__ == "__main__":
    main()
