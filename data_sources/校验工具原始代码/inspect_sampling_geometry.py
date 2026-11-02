"""Inspect the shipped fixed-point mapping, not actual lens accuracy."""
import argparse
import json
from pathlib import Path
import hashlib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def mapping(c, x, y):
    def mul(a, b): return (a * b + 32768) >> 16
    ux = c['A'] * x + c['B'] * y + c['C']
    uy = c['D'] * x + c['E'] * y + c['F']
    r2 = (ux * ux + uy * uy + 32768) >> 16
    xx, yy, xy = mul(ux, ux), mul(uy, uy), mul(ux, uy)
    rad = 65536 + mul(c['k1'], r2) + mul(c['k2'], mul(r2, r2))
    xd = mul(ux, rad) + 2 * mul(c['p1'], xy) + mul(c['p2'], r2 + 2 * xx)
    yd = mul(uy, rad) + mul(c['p1'], r2 + 2 * yy) + 2 * mul(c['p2'], xy)
    return mul(c['fx'], xd) + c['cx'], mul(c['fy'], yd) + c['cy']


def inspect(profile):
    cor = dict(profile['signed_q16_coefficients'])
    raw = dict(cor, k1=0, k2=0, p1=0, p2=0)
    for k in ['A', 'B', 'C', 'D', 'E', 'F', 'fx', 'fy', 'cx', 'cy']:
        assert raw[k] == cor[k]
    x, y = np.meshgrid(np.arange(1280, dtype=np.int64), np.arange(720, dtype=np.int64))
    result = {'simulation_only': True, 'hardware_measured': False, 'lens_model_validated': False,
              'image_size': [1280, 720], 'output_pixels': 921600,
              'raw_cor_base_affine_and_intrinsics_identical': True, 'modes': {}}
    for name, coeff in [('RAW', raw), ('COR', cor)]:
        u, v = mapping(coeff, x, y)
        valid = (u >= 0) & (u <= 1279 * 65536) & (v >= 0) & (v <= 719 * 65536)
        uf, vf = u / 65536, v / 65536
        # Derivatives use spans of 16 pixels to reduce fixed-point stair steps.
        dux = (uf[8:-8, 16:] - uf[8:-8, :-16]) / 16
        duy = (uf[16:, 8:-8] - uf[:-16, 8:-8]) / 16
        dvx = (vf[8:-8, 16:] - vf[8:-8, :-16]) / 16
        dvy = (vf[16:, 8:-8] - vf[:-16, 8:-8]) / 16
        determinant = dux * dvy - duy * dvx
        grid = (slice(None, None, 20), slice(None, None, 20))
        design = np.stack([x[grid].ravel(), y[grid].ravel(), np.ones_like(x[grid]).ravel()], axis=1)
        mapped = np.stack([uf[grid].ravel(), vf[grid].ravel()], axis=1)
        fitted = design @ np.linalg.lstsq(design, mapped, rcond=None)[0]
        residual = np.linalg.norm(mapped - fitted, axis=1)
        entry = {'valid_sample_pixels': int(valid.sum()), 'out_of_frame_pixels': int((~valid).sum()),
            'valid_fraction': float(valid.mean()),
            'left_edge_out_of_frame': int((~valid[:, 0]).sum()),
            'right_edge_out_of_frame': int((~valid[:, -1]).sum()),
            'top_edge_out_of_frame': int((~valid[0]).sum()),
            'bottom_edge_out_of_frame': int((~valid[-1]).sum()),
            'source_coordinate_extent_px': [float(uf.min()), float(uf.max()), float(vf.min()), float(vf.max())],
            'raw_identity_max_error_px': float(np.maximum(np.abs(uf-x), np.abs(vf-y)).max()) if name == 'RAW' else None,
            'mapping_jacobian_determinant_min': float(determinant.min()),
            'best_global_affine_fit_residual_rms_px': float(np.sqrt(np.mean(residual ** 2))),
            'best_global_affine_fit_residual_max_px': float(residual.max())}
        result['modes'][name] = entry
    assert result['modes']['RAW']['raw_identity_max_error_px'] <= .5
    assert result['modes']['COR']['mapping_jacobian_determinant_min'] > 0
    assert result['modes']['COR']['best_global_affine_fit_residual_rms_px'] > 1
    result['interpretation'] = (
        'RAW/COR use the same base affine/intrinsics. Spatially varying radial distortion '
        'changes effective field of view; equal base scale does not mean every source pixel remains visible. '
        'Out-of-frame output is black, not recovered content. A nonzero global affine fit residual '
        'shows the mapping is not only uniform zoom, but does not prove actual lens correction accuracy.')
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists(): ap.error('输出目录已存在')
    source = ROOT / 'targets/selected_empirical_profile.json'
    report = inspect(json.loads(source.read_text(encoding='utf-8')))
    report['profile_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    a.out.mkdir(parents=True)
    (a.out/'sampling.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    text = '# 默认720P采样几何核查\n\n仿真模型检查，不是实测镜头精度。\n\n'
    text += '| 模式 | 有效采样像素 | 越界像素 | 全局仿射拟合残差RMS px |\n|---|---:|---:|---:|\n'
    for name, e in report['modes'].items():
        text += f"| {name} | {e['valid_sample_pixels']} | {e['out_of_frame_pixels']} | {e['best_global_affine_fit_residual_rms_px']:.4f} |\n"
    text += ('\n基础仿射与内参相同；径向变换仍会改变不同区域的局部倍率和有效视野。'
             '非零全局仿射残差说明当前映射不能仅用一次整体缩放解释，不说明系数就是实际镜头真值。'
             '越界取样显示黑色，双线性插值不能恢复视野外内容；本版不额外放大或伪造边缘内容。'
             '有效采样像素数不等于可测物理场景范围，不应当作置信度。\n')
    (a.out/'report.md').write_text(text, encoding='utf-8')
    print(json.dumps(report, indent=2))
