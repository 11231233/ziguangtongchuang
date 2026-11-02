"""Create a separate single-camera project with measured parameters in its RTL.

This does not build or flash. UART is optional for the generated project.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil

from calibration_workflow import ROOT, camera_matrix, model_fingerprint, write_json
from host_control import coefficients
from validate_coefficients import validate


def prepare(calib, validation, out, allow_synthetic_test=False):
    calib, validation, out = Path(calib), Path(validation), Path(out)
    if out.exists():
        raise ValueError('输出目录已存在，请选择新工程目录')
    if any(out.resolve().is_relative_to((ROOT / part).resolve()) for part in ['rtl', 'constr', 'scripts', 'tools', 'targets', 'sim']):
        raise ValueError('新工程不能放入被复制的源码目录内')
    model = json.loads(calib.read_text(encoding='utf-8-sig'))
    report = json.loads(validation.read_text(encoding='utf-8-sig'))
    camera_matrix(model)
    synthetic = model.get('synthetic_test_data') or report.get('synthetic_test_data')
    if synthetic and not allow_synthetic_test:
        raise ValueError('合成数据不能生成真实镜头固件工程')
    if model.get('source_kind_operator_declared') != 'ov5640_raw_digital' and not (synthetic and allow_synthetic_test):
        raise ValueError('必须使用实际OV5640原始数字图的模型')
    camera = model.get('camera')
    if camera not in ('C1', 'C2') or report.get('camera') != camera:
        raise ValueError('模型和独立验证的相机身份不一致')
    source_top = (ROOT / 'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
    single_c1 = 'metrics_osd #(.SINGLE_CAMERA(1))' in source_top
    if single_c1 and camera != 'C1':
        raise ValueError('此工程只有 C1，不能加载 C2 镜头模型')
    if report.get('validation_frames', 0) < 5 or report.get('model_parameters_sha256') != model_fingerprint(model):
        raise ValueError('需要同一模型的至少5张独立验证报告')
    coeff = coefficients(model, roll=0, zoom=1)
    geometry = validate(coeff)
    out.mkdir(parents=True)
    for name in ['rtl', 'constr', 'scripts', 'tools', 'targets', 'sim']:
        shutil.copytree(ROOT / name, out / name,
                        ignore=shutil.ignore_patterns('__pycache__', 'out', 'results'))
    top = out / 'rtl/top/top_pangu50.v'
    text = top.read_text(encoding='utf-8')
    old = "host_active ? host_coeff : {PRE_CY,PRE_CX,PRE_FY,PRE_FX,32'd0,32'd0,PRE_K2,PRE_K1,PRE_F,PRE_E,32'd0,PRE_C,32'd0,PRE_A};"
    def literal(value):
        return f"-32'sd{-value}" if value < 0 else f"32'sd{value}"
    ordered = ['cy', 'cx', 'fy', 'fx', 'p2', 'p1', 'k2', 'k1', 'F', 'E', 'D', 'C', 'B', 'A']
    fields = [f"(local_correction_active?{literal(coeff[k])}:32'sd0)" if k in ('p1', 'p2', 'k1', 'k2') else literal(coeff[k]) for k in ordered]
    new = 'host_active ? host_coeff : {' + ','.join(fields) + '};'
    if text.count(old) != 1:
        raise ValueError('顶层结构已变化，请检查静态系数注入位置')
    text = text.replace(old, new)
    # A measured single-camera profile must never be silently applied to the
    # other camera or the uncalibrated fusion stream. Keep mode and zoom fixed.
    mode_key = '.key_mode_n(mode_key_n)' if '.key_mode_n(mode_key_n)' in text else '.key_mode_n(key6)'
    if (not single_c1 and text.count(mode_key) != 1) or text.count('.key_n({key3,key2,strength_key_n,key0})') != 1:
        raise ValueError('按键结构已变化，请检查单路锁定')
    # The source project can now boot in fusion mode. Target the camera
    # controller instance explicitly, rather than assuming its old default.
    if not single_c1:
        text, selected = re.subn(
            r'(stereo_controls\s*#\(\.DEFAULT_MODE\()\d+(\)[^\n]*?\bu_stereo_controls)',
            lambda m: m[1] + str(1 if camera == 'C1' else 2) + m[2], text)
        if selected != 1:
            raise ValueError('无法唯一定位相机启动选择，拒绝生成错误的单路标定工程')
        text = text.replace(mode_key, ".key_mode_n(1'b1)")
    text = text.replace('.key_n({key3,key2,strength_key_n,key0})', ".key_n({key3,1'b1,1'b1,key0})")
    top.write_text(text, encoding='utf-8')
    record = {'camera': camera, 'calibration_sha256': hashlib.sha256(calib.read_bytes()).hexdigest(),
        'model_parameters_sha256': model_fingerprint(model), 'coefficients': coeff,
        'synthetic_test_data': bool(synthetic), 'hardware_tested': False,
        'image_size': [1280, 720], 'zoom': 1, 'geometry_check': geometry,
        'mode_locked_to_calibrated_camera': True, 'uart_required_for_static_profile': False,
        'fpga_perspective_correction': False, 'warp_per_pixel_confidence': None}
    (out / 'calib').mkdir()
    shutil.copy2(calib, out / 'calib/measured_model.json')
    shutil.copy2(validation, out / 'calib/independent_validation.json')
    write_json(out / 'targets/static_calibrated_profile.json', record)
    (out / 'README.md').write_text(
        '# 静态镜头参数工程\n\n' + ('**合成工具测试，不得作为实测固件。**\n\n' if synthetic else '') +
        f'固定使用{camera}，参数来自calib/measured_model.json，验证报告位于calib/independent_validation.json。'
        '参数编入FPGA，无需串口加载。KEY0同倍率RAW/COR；KEY1短按、KEY2、KEY6禁用，避免改变标定倍率或换用另一镜头。KEY1长按冻结/解除同帧对照。'
        'KEY4长按切Gamma；单目工程短按无动作。标定和几何验收保持G0/T0并关闭OSD。\n\n'
        '```powershell\npython scripts/build.py --name measured_camera_build --seed 2\n```\n\n'
        '本工具只创建源码工程，尚未构建或烧录。构建完成须检查validation.json、时序和板上效果。'
        'targets/selected_empirical_profile.json仅记录保留的本地备用控制模块，不代表顶层实际使用的静态参数；'
        '以targets/static_calibrated_profile.json和顶层注入为准。固定系数不识别现场真实倾斜，不进行透视正视。\n', encoding='utf-8')
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--calib', type=Path, required=True)
    p.add_argument('--validation', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--allow-synthetic-test', action='store_true', help='tool tests only, never measured firmware')
    a = p.parse_args()
    print(json.dumps(prepare(a.calib, a.validation, a.out, a.allow_synthetic_test), ensure_ascii=False, indent=2))
