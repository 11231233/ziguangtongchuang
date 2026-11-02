"""Golden-vector display test: exhaustive color conversion and streaming borders."""
from pathlib import Path
import hashlib,json,random
from verify import test

p=Path(__file__).resolve().parents[1]
out=p/'sim/out';out.mkdir(parents=True,exist_ok=True)
wanted=active=1
previous=(0,0,0,1,0,0,0)
left_pixel=0;left_de=0
samples=0
mode_colors={0:0,1:0,2:0}


def expand(v):
    # Normalized-channel reconstruction, rounded to nearest integer.
    # Bit replication differs from exact scaling by <=1 code value.
    r=(v>>11)&31;g=(v>>5)&63;b=v&31
    return ((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2))


def luma(v):
    r,g,b=expand(v)
    return (r+2*g+b)//4


def put(f,vs=0,hs=0,de=0,cycle=1,pixel=0,osd=0,overlay=0):
    global wanted,active,previous,left_pixel,left_de,samples
    pv,ph,pd,pc,pp,po,pm=previous
    selected=po if pm else pp
    if not pd:
        rgb=0
    elif active==0:
        rgb=(((selected>>11)&31)<<19)|(((selected>>5)&63)<<10)|((selected&31)<<3)
    else:
        channels=expand(selected)
        delta=0
        if active==2 and pd and left_de and de and not pm:
            highpass=2*luma(pp)-luma(left_pixel)-luma(pixel)
            delta=max(-8,min(8,highpass//8))
        channels=tuple(max(0,min(255,c+delta)) for c in channels)
        rgb=(channels[0]<<16)|(channels[1]<<8)|channels[2]
    new_wanted=(wanted+1)%3 if pc and not cycle else wanted
    new_active=wanted if vs and not pv else active
    f.write(f'{vs} {hs} {de} {cycle} {pixel:04x} {osd:04x} {overlay} {pv} {ph} {pd} {rgb:06x} {new_active}\n')
    wanted,active=new_wanted,new_active
    left_pixel,left_de=pp,pd
    previous=(vs,hs,de,cycle,pixel,osd,overlay)
    samples+=1


def boundary(f):
    put(f);put(f,vs=1);put(f,vs=1);put(f)


def select(f,mode):
    while wanted!=mode:
        put(f,cycle=0)
        # Holding the event low must advance once, not every clock.
        for _ in range(7):put(f,cycle=0)
        put(f)
    boundary(f)
    assert active==mode


with (out/'quality_vectors.txt').open('w',encoding='ascii') as f:
    for mode in [0,1,2]:
        select(f,mode)
        for line in range(256):
            for x in range(256):
                value=line*256+x
                put(f,de=1,pixel=value)
                mode_colors[mode]+=1
            put(f,hs=1);put(f,hs=1);put(f);put(f)
        # Constant full white, black and saturated primaries; no false detail.
        for value in [0,0xffff,0xf800,0x07e0,0x001f,0x8410]:
            for _ in range(16):put(f,de=1,pixel=value)
            put(f);put(f)
    rng=random.Random(20261025)
    # Random one-pixel lines and variable blanking stress left/right boundaries.
    for _ in range(128):
        for x in range(rng.randint(1,128)):
            put(f,de=1,pixel=rng.randrange(65536),osd=0xffff if x%2 else 0,overlay=int(x%7==0))
        for _ in range(rng.randint(1,7)):put(f,hs=rng.randrange(2))
    # Request changes during active video; active mode must wait for VS.
    for _ in range(6):
        put(f,de=1,pixel=0x8410,cycle=0)
        for x in range(20):put(f,de=1,pixel=0xffff if x%2 else 0,cycle=0)
        put(f);boundary(f)
    put(f);put(f)

assert all(v==65536 for v in mode_colors.values())
ok=test('quality_display','tb_quality_display',['rtl/video/quality_display.v','sim/tb/tb_quality_display.v'])
report={'passed':ok,'samples':samples,'exhaustive_values_per_mode':mode_colors,
        'source_sha256':{n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in
                         ['rtl/video/quality_display.v','rtl/top/top_pangu50.v','rtl/video/metrics_osd.v']},
        'checks':['Q0 legacy exact','Q1 full-range endpoints','Q2 bounded horizontal detail',
                  'sync and DE latency','line boundaries','overlay protection','mode VS atomicity','held event once'],
        'hardware_image_quality_verified':False}
(p/'reports/quality_display_test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
raise SystemExit(0 if ok else 1)
