from pathlib import Path
from host_control import FIELDS,packet
p=Path(__file__).resolve().parents[1]/'sim/out'
c=dict(zip(FIELDS,(126,-60,-59000,60,126,-85000,-18350,5243,180,-90,34078720,34078720,41943040,23592960)))
data=packet(c,37)
(p/'host_packet.hex').write_text('\n'.join(f'{v:02x}' for v in data)+'\n')
(p/'host_coeff.hex').write_text(''.join(f'{c[k]&0xffffffff:08x}' for k in reversed(FIELDS))+'\n')
print('HOST vectors:',len(data),'bytes, affine rotation and nonzero tangential terms')
