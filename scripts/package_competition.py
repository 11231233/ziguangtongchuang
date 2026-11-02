"""Bind current offline checks and unchanged firmware to a reviewable release."""
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def checked_manifest(manifest):
    return [name for name,digest in manifest.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]

def main():
    baseline=load(ROOT/'evidence/baseline_20261027/manifest_image30.json')
    mismatch=checked_manifest(baseline['input_sha256'])
    if mismatch: raise SystemExit('Baseline build inputs changed; rebuild PDS: '+str(mismatch))
    firmware=ROOT/'firmware'/baseline['firmware']
    if sha(firmware)!=baseline['firmware_sha256']: raise SystemExit('Firmware hash mismatch')
    host=load(ROOT/'reports/host_validation_20261029.json')
    rtl=load(ROOT/'reports/image30_regression.json')
    if not (host.get('complete') and host.get('passed') and rtl.get('complete') and rtl.get('passed')):
        raise SystemExit('Current host/RTL checks incomplete or failed')
    full_candidates=sorted((ROOT/'sim/results').glob('full720_*/result.json'))
    full_path=full_candidates[-1]
    full=load(full_path)
    if not (full.get('passed') and full.get('exact_compared_pixels')==921600 and full.get('selected_preset') and full.get('shared_capture_display_ddr_modeled')):
        raise SystemExit('Full720 check failed or not current preset/shared DDR')
    if checked_manifest(full['rtl_sha256']): raise SystemExit('RTL differs from Full720 test')
    if full['preset_sha256']!=sha(ROOT/'targets/selected_empirical_profile.json'): raise SystemExit('Preset differs from Full720 test')
    regressions=sorted(p for p in (ROOT/'sim/results').glob('*/summary.json') if p.parent.name[:8]=='20261029')
    regression_path=regressions[-1]
    regression=load(regression_path)
    if not (regression.get('passed') and regression.get('complete')) or checked_manifest(regression['rtl_sha256']):
        raise SystemExit('40-case RTL summary does not bind to current RTL')
    old=load(ROOT/'evidence/baseline_20261027/reports/image30_board_60s.json')
    release=dict(schema='competition_review_v1',created=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                 release_kind='host_tools_and_delivery_update_with_unchanged_fpga_firmware',
                 firmware=firmware.relative_to(ROOT).as_posix(),firmware_sha256=sha(firmware),
                 baseline_build_inputs_match=True,pds_evidence_inherited=True,pds_rebuilt_this_revision=False,
                 configured_constraints_only=True,dvp_input_delay_constraints_complete=False,
                 host_validation='reports/host_validation_20261029.json',host_checks=len(host['checks']),
                 rtl_validation=regression_path.relative_to(ROOT).as_posix(),rtl_tests=len(regression['tests']),
                 full720_validation=full_path.relative_to(ROOT).as_posix(),compared_pixels=921600,
                 real_board_test_performed_this_revision=False,real_calibration_completed=False,
                 physical_image_quality_verified=False,hardware_dynamic_demo_verified=False,
                 end_to_end_latency_ms=None,competition_all_requirements_satisfied=False,
                 baseline_completed_fps=old['completed_fps_serial_estimate'],baseline_30fps_passed=old['passed'],
                 resolution=[1280,720],hdmi_refresh_hz=60,official_1080p_requirement_confirmed=False)
    (ROOT/'release_manifest.json').write_text(json.dumps(release,ensure_ascii=False,indent=2),encoding='utf-8')
    text=f'''# 交付校验结果

- 上位机离线检查：{len(host['checks'])}组通过，含测量、扫角、标定、参数导入、直线度及SFR工具。合成数据仅用于工具测试。
- 完整RTL回归：{len(regression['tests'])}项通过；增强、84MHz采集、串口和显示专项回归也通过。
- 完整720P：921600像素逐一与参考一致，含共享采集/显示DDR背景及随机等待；仿真不是实板帧率证明。
- 本次FPGA输入源码和约束与原PDS构建清单全部一致，原固件SHA256复核一致。本次没有修改RTL、重新构建PDS或烧录。
- 固件SHA256：`{sha(firmware)}`。
- 既有PDS资源：FF17108、LUT15383、DRM27、APM61、分布式RAM362。已配置时序通过证据继承自2026-10-27；外部DVP输入延迟仍未完整约束。
- 原实测{old['completed_fps_serial_estimate']:.6f}fps仍未达工程30fps验收条件。没有新实板数据；真实标定、MTF、端到端延迟、动态与光照验收待补。

本版本软件完善并通过上述离线验证；**竞赛全部达标状态为否**。详见release_manifest.json及赛题要求对应与性能分析.md。
'''
    (ROOT/'docs/交付校验结果.md').write_text(text,encoding='utf-8')
    # Include source and evidence, excluding transient build products and stale
    # root-level reports that were copied from the historical project.
    selected=[]
    for directory in ('rtl','constr','scripts','tools','targets','calib','firmware','docs','evidence','sim/tb','sim/model'):
        selected += [p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for result_folder in (full_path.parent,regression_path.parent):
        selected += [p for p in result_folder.rglob('*') if p.is_file()]
    report_names=['reports/image30_regression.json','reports/regression_20261029.log','reports/full720_20261029.log','reports/host_validation_20261029.json','reports/host_validation_20261029.log','reports/baseline_receive_analysis.json']
    report_names += [c['log'] for c in host['checks']]
    selected += [ROOT/name for name in report_names]
    selected += [ROOT/name for name in ('README.md','release_manifest.json','30帧连续检测.cmd','启动标定与上位机.cmd')]
    selected=sorted(set(selected))
    checksums={p.relative_to(ROOT).as_posix():sha(p) for p in selected}
    (ROOT/'delivery_manifest.json').write_text(json.dumps(dict(schema='delivery_files_v1',sha256=checksums),ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'SHA256SUMS.txt').write_text(''.join(d+'  '+name+'\n' for name,d in checksums.items()),encoding='utf-8')
    selected += [ROOT/'delivery_manifest.json',ROOT/'SHA256SUMS.txt']
    archive=ROOT.parent/'competition_20261029_delivery.zip'
    if archive.exists(): raise SystemExit('Archive already exists; preserve it and choose a new release name')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for path in selected: z.write(path,Path(ROOT.name)/path.relative_to(ROOT))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise SystemExit('Archive CRC failure')
        for name,digest in checksums.items():
            if hashlib.sha256(z.read(ROOT.name+'/'+name)).hexdigest()!=digest:
                raise SystemExit('Archive content mismatch: '+name)
    (archive.with_suffix('.zip.sha256')).write_text(sha(archive)+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps(dict(archive=str(archive),sha256=sha(archive),files=len(selected),offline_checks_passed=True,competition_all_requirements_satisfied=False),ensure_ascii=False))

if __name__=='__main__': main()
