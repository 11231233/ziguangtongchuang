"""Exercise compact RAW windows with scaling and all four source edges."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess,sys
from verify import test,env

p=Path(__file__).resolve().parents[1]
out=p/'reports/revision6/raw_window_edges';out.mkdir(parents=True,exist_ok=False)
manifest={f.relative_to(p).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'rtl').rglob('*.v')}
files=[f.relative_to(p).as_posix() for f in (p/'rtl/warp').glob('*.v') if f.name not in ['line_ring.v','tile_fetch.v']]+['sim/tb/tb_full.v']
results=[]
for name,scale,x,y in [('compact',.8125,20,5),('expanded',1.5,-20,-10),('right_bottom',1,80,50),('left_top',1,-100,-60)]:
    subprocess.run([sys.executable,str(p/'tools/gen_full_reference.py'),'--axis-scale',str(scale),'--axis-x',str(x),'--axis-y',str(y)],check=True,env=env)
    ok=test('raw_edge_'+name,'tb_full',files)
    for src,dst in [(f'raw_edge_{name}.log',f'{name}.log'),(f'raw_edge_{name}_compile.log',f'{name}_compile.log'),('frame_coef.vh',f'{name}_coeff.vh')]:shutil.copy2(p/'sim/out'/src,out/dst)
    results.append({'case':name,'scale':scale,'offset':[x,y],'passed':ok,'exact_compared_pixels':8960 if ok else 0})
    if not ok:raise SystemExit('RAW WINDOW EDGE FAILED: '+name)
assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
(out/'summary.json').write_text(json.dumps({'passed':True,'simulation_only':True,'cases':results,'rtl_sha256':manifest},indent=2),encoding='utf-8')
print('RAW WINDOW EDGES PASS:',len(results),'cases; exact pixels and fetched-neighbour bounds')
