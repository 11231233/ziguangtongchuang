from pathlib import Path
import json,hashlib
r=Path(__file__).resolve().parents[1]
m=json.loads((r/'provenance/original_gui_source_sha256.json').read_text())
diff=[n for n,h in m.items() if hashlib.sha256((r/n).read_bytes()).hexdigest()!=h]
assert diff==['rtl/top/top_pangu50.v'],diff
old=(r/'provenance/top_pangu50.v').read_text(encoding='utf-8')
expected=old.replace('F:/wancheng_ziguang_jibian_codex/rtl/warp/radial_lut.hex','rtl/warp/radial_lut.hex')
assert expected==(r/'rtl/top/top_pangu50.v').read_text(encoding='utf-8')
assert hashlib.sha256((r/'firmware/top_pangu50.sbit').read_bytes()).hexdigest()=='47b43f71cbda3bf63dd16e16297099ce8aecd916b6e1726e8db95007cbf36046'
print('PASS: original source, LUT, calibration controls and firmware preserved; only ROM path relocated.')
