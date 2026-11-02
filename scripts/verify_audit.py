"""Audit regressions, including negative reproducers against the parent RTL."""
from pathlib import Path
import binascii,hashlib,json,struct
from verify import test

root=Path(__file__).resolve().parents[1]
out=root/'sim/out';out.mkdir(exist_ok=True)
profile=json.loads((root/'targets/selected_empirical_profile.json').read_text())['signed_q16_coefficients']
names=['A','B','C','D','E','F','k1','k2','p1','p2','fx','fy','cx','cy']
packets=[]
def encode(c,seq):
    body=bytes([1,seq])+struct.pack('<14i',*[c[n] for n in names])
    return b'\xa5\x5a'+body+struct.pack('>H',binascii.crc_hqx(body,0xffff))
packets.append(encode(profile,17))
for n,value,seq in [('A',131072,18),('A',-131073,19),('k1',262144,20),('fx',0,21),('fy',-1,22),('A',126,0)]:
    packets.append(encode(dict(profile,**{n:value}),seq))
packets.append(encode(profile,31))
packets.append(encode(dict(profile,A=-131072,k1=131071),42))
(out/'audit_host_ranges.hex').write_text('\n'.join(f'{b:02x}' for b in b''.join(packets))+'\n',encoding='ascii')
checks=[
 ('hub_acceptance','tb_hub_acceptance',['rtl/mem/mem_hub.v','sim/tb/tb_hub_acceptance.v']),
 ('host_ranges','tb_host_ranges',['rtl/common/warp_config.v','sim/tb/tb_host_ranges.v']),
 ('three_slots','tb_three_slots',['rtl/common/async_fifo.v','rtl/mem/frame_writer.v','rtl/common/warp_scheduler.v','sim/tb/tb_three_slots.v']),
 ('window_bounds','tb_window_bounds',['rtl/warp/bilinear_2x2.v','rtl/warp/warp_tile_stream.v','sim/tb/tb_window_bounds.v']),
 ('axi_bursts','tb_axi_bursts',['rtl/mem/axi_ddr_master.v','sim/tb/tb_axi_bursts.v'])]
results=[]
for name,top,files in checks:
    ok=test(name,top,files)
    results.append(dict(name=name,passed=ok))
    if not ok:raise SystemExit('Audit failed: '+name)
parent=root/'sim/model/audit_parent'
repro=[]
for name,top,files in checks[:2]:
    original=[str(parent/Path(files[0]).name),files[1]]
    ok=test('parent_'+name,top,original)
    log=(out/('parent_'+name+'.log')).read_text(errors='replace')
    signature='CLIENT ACK BEFORE DDR ACCEPTANCE' if name=='hub_acceptance' else 'INVALID COEFFICIENT BANK COMMITTED'
    assert not ok and signature in log,'Expected baseline defect was not reproduced: '+name
    repro.append(dict(name=name,baseline_reproduced=True,failure=signature,corrected_version_passed=True))
report=dict(passed=True,simulation_only=True,tests=results,parent_reproducers=repro,
    source_sha256={str(f.relative_to(root)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in (root/'rtl').rglob('*.v')})
(root/'reports/audit_tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('AUDIT PASS: exact acceptance, valid-CRC rejection, 100-frame three-slot stress, fetched-window bounds; two baseline defects reproduced')
