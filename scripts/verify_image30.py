from pathlib import Path
import json,subprocess,sys
p=Path(__file__).resolve().parents[1]
checks=['verify_image30_config.py','verify_quality_natural.py','verify_quality_display.py','verify_quality_controls.py','verify_single_uart.py','verify_single_uart_84m.py','verify_display_pipeline.py','verify_sensor_diag.py','verify_fps30.py','verify_audit.py','check_profile_sync.py','check_structure.py','verify_all.py']
results=[]
for name in checks:
 print('RUN',name,flush=True)
 r=subprocess.run([sys.executable,str(p/'scripts'/name)],cwd=p)
 results.append({'script':name,'passed':r.returncode==0})
 (p/'reports/image30_regression.json').write_text(json.dumps({'passed':False,'complete':False,'checks':results},indent=2))
 if r.returncode:raise SystemExit('FAILED '+name)
(p/'reports/image30_regression.json').write_text(json.dumps({'passed':True,'complete':True,'checks':results},indent=2))
print('IMAGE30 REGRESSION PASS',flush=True)
