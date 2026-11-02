"""Validate four isolated simulations and report the RAW fetch optimization."""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/revision6'


def collect():
    before_hash=json.loads((ROOT/'reports/revision5/rtl_regression_40.json').read_text())['rtl_sha256']
    after_hash={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'rtl').rglob('*.v')}
    analytical=json.loads((OUT/'analytical_traffic/window_traffic.json').read_text())
    records={}
    for version, hashes in [('baseline',before_hash),('optimized',after_hash)]:
        for mode in ['raw','cor']:
            name=f'perf_v6_{version}_{mode}'
            root=ROOT/'verification'/name/'sim/results'
            f=max(root.glob('full720_*/result.json'),key=lambda p:p.stat().st_mtime)
            data=json.loads(f.read_text())
            assert data['passed'] and data['exact_compared_pixels']==921600 and data['shared_capture_display_ddr_modeled'],name
            assert data['matched_raw']==(mode=='raw') and data['rtl_sha256']==hashes,name
            log=(f.parent/'full720.log').read_text()
            cycles=re.findall(r'FULL_FRAME PASS:[^\n]*;\s*cycles=\s*(\d+)',log)
            assert len(cycles)==1,name
            # The original loose "cycles=" parser also matched overlap_cycles
            # after counters were added. Re-extract solely from completion line.
            cycles=int(cycles[0])
            counters={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',re.findall(r'^PERF (.+)$',log,re.M)[-1])}
            expected=analytical['modes'][mode.upper()]['before' if version=='baseline' else 'after']
            assert counters['rd_requests']==expected['read_requests'] and counters['rd_beats']==expected['read_beats_256bit'],name
            destination=OUT/name;destination.mkdir(parents=True,exist_ok=True)
            if data['frame_cycles']!=cycles:
                shutil.copy2(f,destination/'result_before_cycle_parser_fix.json')
                data.update(frame_cycles=cycles,isolated_engine_fps=100000000/cycles,
                    meets_60fps_in_this_model=cycles<=100000000/60,
                    cycle_parser_corrected_from_full_frame_completion_line=True)
            data['performance_counters']=counters
            (destination/'result.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
            for n in ['full720.log','full720_compile.log','frame_coef.vh']:shutil.copy2(f.parent/n,destination/n)
            records[name]={'frame_cycles':cycles,'model_processing_ms':cycles/100000,
                'read_requests':counters['rd_requests'],'read_beats_256bit':counters['rd_beats'],
                'read_bytes':counters['rd_beats']*32,'performance_counters':counters,
                'exact_compared_pixels':921600,'hardware_measured':False}
    old,new=records['perf_v6_baseline_raw'],records['perf_v6_optimized_raw']
    cor0,cor1=records['perf_v6_baseline_cor'],records['perf_v6_optimized_cor']
    assert cor0['frame_cycles']==cor1['frame_cycles'] and cor0['read_bytes']==cor1['read_bytes']
    assert new['frame_cycles']<old['frame_cycles'] and new['read_bytes']<old['read_bytes']
    summary={'passed':True,'simulation_only':True,'hardware_measured':False,
        'raw_frame_cycle_reduction_percent':100*(old['frame_cycles']-new['frame_cycles'])/old['frame_cycles'],
        'raw_read_byte_reduction_percent':100*(old['read_bytes']-new['read_bytes'])/old['read_bytes'],
        'cor_model_cycles_and_traffic_unchanged':True,'records':records,
        'user_reported_observation':{'RAW_CALC_ms':'around 38','COR_CALC_ms':'around 30',
            'firmware_sha256_confirmed':False,'agent_measured':False},
        'scope':'Counters measure simulated warp-window reads only, not total DDR traffic or end-to-end latency. '
            'Counters overlap; do not add them as a cycle partition. Actual CALC improvement requires board measurement.'}
    (OUT/'performance_comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    text='# RAW取样窗口优化对照\n\n四组均为仿真，不是实板时延。每组921600像素与独立参考精确一致，含模拟采集/显示DDR背景负载。\n\n'
    text+='| 模式 | 模型完整帧周期 | 模型处理ms（100MHz） | 读取请求 | 读取字节（仅畸变引擎） |\n|---|---:|---:|---:|---:|\n'
    for name,rec in records.items():
        text+=f"| {name} | {rec['frame_cycles']} | {rec['model_processing_ms']:.4f} | {rec['read_requests']} | {rec['read_bytes']} |\n"
    text+=(f"\nRAW模型周期减少{summary['raw_frame_cycle_reduction_percent']:.2f}%，读取字节减少{summary['raw_read_byte_reduction_percent']:.2f}%；COR模型周期和取样量不变。\n\n"
        '仅对零畸变、正向轴对齐映射收紧窗口。坐标、双线性插值、输出倍率和像素结果保持一致；带旋转或非零畸变的情况继续使用原保护边界。'
        '边缘窗口按实际剩余行列限制，逐像素断言检查真实取入缓存的邻点范围。\n\n'
        '扩展性能字段后，旧周期解析规则误匹配overlap_cycles；本报告只从FULL_FRAME PASS完成行提取总周期，保留原JSON和原始日志。'
        '这不影响像素比对或RTL仿真，不能把修正前的派生FPS当测量结果。\n\n'
        '用户反馈RAW约38ms/COR约30ms仅记录为用户观察，尚未确认固件哈希或进行优化后实测；不可把模型百分比直接套算为新版实板时延。'
        '模型未含真实DDR PHY；CALC不含曝光、采集、融合与显示完整延迟，H1输出是固定源重算。\n')
    (OUT/'性能对照.md').write_text(text,encoding='utf-8')
    return summary


if __name__=='__main__':
    print(json.dumps(collect(),indent=2))
