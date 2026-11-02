"""Digital-frame calibration sessions. Hardware provenance is operator-declared.

No phone-screen images, synthetic parameters or PC previews are promoted to
measured FPGA results. Saved training frames always come from the raw input.
"""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
from checkerboard_detection import detect_checkerboard, diagnose_partial_board, CheckerboardNotFound

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1280, 720)


def stamp():
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def read_image(path):
    im = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError('无法读取图像：' + str(path))
    return im


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def load_session(folder):
    folder = Path(folder)
    data = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
    if data.get('schema') != 'ov5640_digital_session_v1':
        raise ValueError('不是数字取图标定会话')
    return data


def create_session(folder, camera, cols, rows, square_mm, confirmed, synthetic=False):
    folder = Path(folder)
    if folder.exists():
        raise ValueError('目录已存在；创建新目录以保留记录')
    if camera not in ('C1', 'C2') or min(cols, rows) < 3:
        raise ValueError('请选择C1/C2和正确的棋盘内角点数')
    if not math.isfinite(square_mm) or square_mm <= 0:
        raise ValueError('需要填写实测单格边长（毫米）')
    if not confirmed:
        raise ValueError('须先确认数字取图、RAW/G0/T0、单路、无OSD、无缩放裁切及固定镜头模式')
    folder.mkdir(parents=True)
    for part in ('train', 'validation'):
        (folder / part).mkdir()
    data = {'schema': 'ov5640_digital_session_v1', 'created': stamp(),
            'camera': camera, 'image_size': list(SIZE), 'inner_corners': [cols, rows],
            'square_mm_operator_measured': square_mm,
            'capture_conditions_operator_confirmed': True,
            'capture_provenance_verified_by_tool': False,
            'source_kind_operator_declared': 'synthetic' if synthetic else 'ov5640_raw_digital',
            'synthetic_test_data': synthetic, 'frames': [],
            'real_lens_calibration_complete': False}
    write_json(folder / 'session.json', data)
    return data


def corners(image, pattern):
    return detect_checkerboard(image, pattern)['points']


def write_checkerboard_check(image, pattern, out, detection=None, error=None):
    out = Path(out)
    if out.exists():
        raise ValueError('棋盘检查输出已存在，请使用新目录')
    out.mkdir(parents=True)
    overlay = image.copy()
    report = {'found': detection is not None, 'expected_inner_corners': list(pattern),
              'expected_count': int(pattern[0] * pattern[1]),
              'detected_count': len(detection['points']) if detection is not None else 0,
              'image_size': [image.shape[1], image.shape[0]],
              'training_frame_saved': False, 'partial_grid_is_training_data': False}
    if detection is not None:
        report.update(method=detection['method'], attempts=detection['attempts'],
                      points=detection['points'].tolist())
        cv2.drawChessboardCorners(overlay, tuple(pattern),
                                 detection['points'].reshape(-1, 1, 2), True)
        report['message'] = f'完整棋盘识别成功：{report["detected_count"]}/{report["expected_count"]}个内角点。此检查不自动保存训练帧。'
    else:
        report['attempts'] = getattr(error, 'attempts', [])
        report['message'] = str(error)
        partial = diagnose_partial_board(image)
        report['partial_candidate'] = partial
        if partial:
            pts = np.asarray(partial['points'], np.float32).reshape(-1, 1, 2)
            cv2.drawChessboardCorners(overlay, tuple(partial['inner_corners']), pts, True)
            report['message'] += (f'\n另找到{partial["corner_count"]}点的候选局部网格，'
                                  '不能代替当前设置的完整棋盘。')
            cv2.putText(overlay, f'PARTIAL ONLY: {partial["corner_count"]}/{report["expected_count"]}',
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
    for name, pixels in [('original.png', image), ('overlay.png', overlay)]:
        ok, encoded = cv2.imencode('.png', pixels)
        if not ok:
            raise ValueError('棋盘诊断PNG编码失败')
        (out / name).write_bytes(encoded.tobytes())
    report.update(original_image=str((out / 'original.png').resolve()),
                  overlay_image=str((out / 'overlay.png').resolve()),
                  report_path=str((out / 'report.json').resolve()))
    write_json(out / 'report.json', report)
    return report


def check_checkerboard(image, pattern, out):
    try:
        detection = detect_checkerboard(image, pattern)
    except CheckerboardNotFound as error:
        return write_checkerboard_check(image, pattern, out, error=error)
    return write_checkerboard_check(image, pattern, out, detection=detection)


def save_frame(folder, image, split, source):
    folder = Path(folder)
    session = load_session(folder)
    if split not in ('train', 'validation'):
        raise ValueError('用途必须为train或validation')
    if image is None or image.dtype != np.uint8 or image.shape != (720, 1280, 3):
        raise ValueError('仅接受未缩放1280×720、8位三通道数字帧')
    image = np.ascontiguousarray(image)
    pixel_hash = digest(image.tobytes())
    if any(f['pixel_sha256'] == pixel_hash for f in session['frames']):
        raise ValueError('这张图已保存；不能重复计入训练集或验证集')
    try:
        detection = detect_checkerboard(image, session['inner_corners'])
    except CheckerboardNotFound as error:
        report = write_checkerboard_check(image, session['inner_corners'],
            folder / 'diagnostics' / ('checkerboard_' + stamp()), error=error)
        raise ValueError(report['message'] + '\n原图和角点检查已保存：' + report['report_path']) from None
    pts = detection['points']
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise ValueError('PNG编码失败')
    name = f'{split}/{stamp()}.png'
    (folder / name).write_bytes(encoded.tobytes())
    rec = {'file': name, 'split': split, 'saved': stamp(), 'source': str(source),
           'sha256': digest(encoded.tobytes()), 'pixel_sha256': pixel_hash,
           'corner_detector': detection['method'],
           'board_center_fraction': (pts.mean(axis=0) / np.array(SIZE)).tolist(),
           'board_extent_fraction': (np.ptp(pts, axis=0) / np.array(SIZE)).tolist(),
           'laplacian_variance': float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())}
    session['frames'].append(rec)
    write_json(folder / 'session.json', session)
    return rec


def check_files(folder, data):
    seen = set()
    for rec in data['frames']:
        path = Path(folder) / rec['file']
        if digest(path.read_bytes()) != rec['sha256']:
            raise ValueError('图像文件与采集记录不符：' + str(path))
        pixel_hash = digest(np.ascontiguousarray(read_image(path)).tobytes())
        if pixel_hash != rec['pixel_sha256'] or pixel_hash in seen:
            raise ValueError('图像像素被修改或重复：' + str(path))
        seen.add(pixel_hash)


def camera_matrix(model):
    if model.get('image_size') != list(SIZE):
        raise ValueError('模型必须对应1280×720')
    values = [model[k] for k in ('fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'p1', 'p2')]
    if not np.isfinite(values).all() or min(values[:2]) <= 0 or abs(model.get('k3', 0)) > 1e-9:
        raise ValueError('模型数值无效或含FPGA未实现的k3')
    K = np.array([[model['fx'], 0, model['cx']], [0, model['fy'], model['cy']], [0, 0, 1]], np.float64)
    d = np.array([model[k] for k in ('k1', 'k2', 'p1', 'p2')] + [0.0], np.float64)
    return K, d


def model_fingerprint(model):
    keys = ('fx', 'fy', 'cx', 'cy', 'k1', 'k2', 'p1', 'p2')
    values = {k: float(model[k]) for k in keys}
    values['image_size'] = model['image_size']
    values['k3'] = float(model.get('k3', 0))
    return digest(json.dumps(values, sort_keys=True, allow_nan=False).encode('utf-8'))


def remap_preview(image, model):
    K, d = camera_matrix(model)
    maps = cv2.initUndistortRectifyMap(K, d, None, K, SIZE, cv2.CV_32FC1)
    return cv2.remap(image, *maps, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def plane_preview(image, model, pattern):
    """Host-only front view of a known plane, never a claim of FPGA homography."""
    K, d = camera_matrix(model)
    pts = corners(image, pattern)
    pts = cv2.undistortPoints(pts.reshape(-1, 1, 2), K, d, P=K).reshape(pattern[1], pattern[0], 2)
    spacing = float(np.median(np.linalg.norm(np.diff(pts, axis=1), axis=2)))
    spacing = min(spacing, 1100 / (pattern[0] - 1), 600 / (pattern[1] - 1))
    target = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2).astype(np.float32) * spacing
    target += np.array(SIZE) / 2 - np.array([pattern[0] - 1, pattern[1] - 1]) * spacing / 2
    H, _ = cv2.findHomography(pts.reshape(-1, 2), target, method=0)
    if H is None:
        raise ValueError('无法求平面透视变换')
    return cv2.warpPerspective(remap_preview(image, model), H, SIZE)


def validate(folder, model, out):
    """Held-out observations; fit only each new board pose, never refit K/d."""
    from check_board_straightness import measure
    folder, out = Path(folder), Path(out)
    data = load_session(folder)
    check_files(folder, data)
    if out.exists():
        raise ValueError('验证输出目录已存在')
    K, d = camera_matrix(model)
    pattern = data['inner_corners']
    obj = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    obj[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2) * data['square_mm_operator_measured']
    trained = set(model.get('input_images_sha256', {}).values())
    records = [f for f in data['frames'] if f['split'] == 'validation']
    if len(records) < 5:
        raise ValueError('至少需要5张独立验证图，不得从训练图重复复制')
    results = []
    for rec in records:
        if rec['sha256'] in trained:
            raise ValueError('验证图参与过模型拟合，不能称为独立验证')
        im = read_image(folder / rec['file'])
        pts = corners(im, pattern)
        ok, rv, tv = cv2.solvePnP(obj, pts, K, d)
        if not ok:
            raise ValueError('验证姿态求解失败：' + rec['file'])
        pred, _ = cv2.projectPoints(obj, rv, tv, K, d)
        residual = pred.reshape(-1, 2) - pts
        und = cv2.undistortPoints(pts.reshape(-1, 1, 2), K, d, P=K).reshape(-1, 2)
        raw_lines = measure(pts, *pattern)
        cor_lines = measure(und, *pattern)
        results.append({'file': rec['file'], 'sha256': rec['sha256'],
            'reprojection_rms_px': float(np.sqrt(np.mean(np.sum(residual ** 2, axis=1)))),
            'max_reprojection_error_px': float(np.linalg.norm(residual, axis=1).max()),
            'raw_normalized_line_rms': raw_lines['mean_line_rms_fraction_of_spacing'],
            'corrected_corner_normalized_line_rms': cor_lines['mean_line_rms_fraction_of_spacing']})
    out.mkdir(parents=True)
    all_rms = np.array([v['reprojection_rms_px'] for v in results])
    report = {'camera': data['camera'], 'synthetic_test_data': data['synthetic_test_data'],
        'model_parameters_sha256': model_fingerprint(model),
        'source_kind_operator_declared': data['source_kind_operator_declared'],
        'capture_provenance_verified_by_tool': False, 'validation_frames': len(results),
        'held_out_reprojection_rms_px': float(np.sqrt(np.mean(all_rms ** 2))),
        'max_view_rms_px': float(all_rms.max()), 'per_view': results,
        'fpga_hardware_tested': False, 'competition_acceptance_pass': None,
        'warp_per_pixel_confidence': None,
        'scope': 'Fixed K/distortion on held-out images; only target pose fitted per image. '
                 'Line metrics use mapped observed corners, not a fresh detection in FPGA output. '
                 'No absolute world geometry, pixel confidence, latency or resolution guarantee.'}
    write_json(out / 'validation.json', report)
    text = '# 独立验证报告\n\n'
    if data['synthetic_test_data']:
        text += '**合成工具测试数据，不能作为真实镜头或实板证据。**\n\n'
    text += (f"相机：{data['camera']}；验证图：{len(results)}；留出重投影RMS："
             f"{report['held_out_reprojection_rms_px']:.4f}px；逐图最大RMS：{report['max_view_rms_px']:.4f}px。\n\n"
             'K和畸变系数保持固定，仅拟合每张验证图的标定板姿态。倾斜、正常透视被允许；不把水平或90度作为验收目标。\n\n'
             '| 验证图 | 重投影RMS px | 原角点直线RMS/格距 | 映射后角点直线RMS/格距 |\n|---|---:|---:|---:|\n')
    for rec in results:
        text += f"| {rec['file']} | {rec['reprojection_rms_px']:.4f} | {rec['raw_normalized_line_rms']:.6f} | {rec['corrected_corner_normalized_line_rms']:.6f} |\n"
    text += ('\n这是上位机模型验证，不是FPGA输出实测。来源和固定条件仍为人工声明；没有自动判定比赛达标。'
             '重复和修改图像按哈希检查；视觉近似重复、板不平整、焦点变化仍须人工审核。'
             '没有计算逐像素校正置信度，也没有测量真实尺寸或三维场景真值。\n')
    (out / 'report.md').write_text(text, encoding='utf-8')
    return report


def calibrate(folder):
    folder = Path(folder).resolve()
    data = load_session(folder)
    check_files(folder, data)
    train = [f for f in data['frames'] if f['split'] == 'train']
    val = [f for f in data['frames'] if f['split'] == 'validation']
    if len(train) < 10 or len(val) < 5:
        raise ValueError(f'当前训练{len(train)}张、验证{len(val)}张；至少10+5，建议15—25张训练图及5—10张验证图')
    # The legacy calibrator accepts a glob: require exact agreement with the
    # manifest, preventing unrecorded files from silently entering training.
    listed = {str((folder / f['file']).resolve()) for f in train}
    actual = {str(f.resolve()) for f in (folder / 'train').glob('*.png')}
    if listed != actual:
        raise ValueError('train目录与采集清单不一致，不能混入未记录图像')
    out = folder / 'results' / stamp()
    out.mkdir(parents=True)
    command = [sys.executable, str(ROOT / 'tools/calib_ov5640.py'),
        '--images', str(folder / 'train/*.png'), '--cols', str(data['inner_corners'][0]),
        '--rows', str(data['inner_corners'][1]), '--square', str(data['square_mm_operator_measured']),
        '--source-kind', data['source_kind_operator_declared'], '--out', str(out / 'calibration.json'),
        '--report', str(out / 'calibration_report.md')]
    env = os.environ.copy(); env['PYTHONIOENCODING'] = 'utf-8'
    job = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    (out / 'calibration.log').write_text(job.stdout + job.stderr, encoding='utf-8')
    if job.returncode:
        raise ValueError('标定失败，详见：' + str(out / 'calibration.log') + '\n' + job.stderr[-1000:])
    model = json.loads((out / 'calibration.json').read_text(encoding='utf-8'))
    model['camera'] = data['camera']
    model['session_manifest_sha256'] = digest((folder / 'session.json').read_bytes())
    write_json(out / 'calibration.json', model)
    validation = validate(folder, model, out / 'validation')
    write_json(out / 'session_snapshot.json', data)
    # Numerical calibration is available, but never self-certify real accuracy.
    data['latest_result'] = str(out)
    data['real_lens_calibration_complete'] = False
    data['calibration_model_estimated'] = True
    data['independent_validation_available'] = True
    write_json(folder / 'session.json', data)
    return out, validation
