#!/usr/bin/env python3
"""Send small affine/calibration packets; no coordinate maps leave the FPGA."""
import argparse
import binascii
import json
import math
from pathlib import Path
import struct
import time
import secrets

FIELDS = ('A','B','C','D','E','F','k1','k2','p1','p2','fx','fy','cx','cy')

def packet(coeff, sequence=1):
    values = [int(coeff[k]) for k in FIELDS]
    for k,v in zip(FIELDS,values):
        if not -(1<<31) <= v < (1<<31):
            raise ValueError(f'{k}: exceeds signed Q16.16')
        if k in ('A','B','D','E','k1','k2','p1','p2') and not -131072 <= v < 131072:
            raise ValueError(f'{k}: exceeds RTL signed 18-bit coefficient range')
    body = bytes((1,sequence & 255)) + struct.pack('<14i',*values)
    return b'\xa5\x5a' + body + struct.pack('>H',binascii.crc_hqx(body,0xffff))

def coefficients(calib, roll=0, zoom=1, yaw=0, pitch=0, raw=False):
    from warp_model import CamParams,OutGeom,WarpParams,s32
    if not all(math.isfinite(v) for v in (roll,zoom,yaw,pitch)) or zoom <= 0:
        raise ValueError('angles must be finite and zoom must be positive')
    if raw:
        return dict(zip(FIELDS,(128,0,0,0,128,0,0,0,0,0,33554432,33554432,0,0)))
    if calib.get('image_size',[1280,720]) != [1280,720]:
        raise ValueError('calibration must match the 1280x720 source')
    if abs(calib.get('k3',0)) > 1e-9:
        raise ValueError('FPGA has no k3 term: recalibrate with CALIB_FIX_K3')
    cam=CamParams(**{k:calib[k] for k in ('fx','fy','cx','cy','k1','k2','p1','p2')})
    if cam.fx <= 0 or cam.fy <= 0:raise ValueError('focal length must be positive')
    wp=WarpParams(cam=cam,out=OutGeom(fx=cam.fx,fy=cam.fy,cx=cam.cx,cy=cam.cy),
                  roll_deg=roll,zoom=zoom,yaw_deg=yaw,pitch_deg=pitch)
    return {k:s32(v) for k,v in wp.coeffs().items()}

def read_status(port, seconds, expected_sequence=None, roll_deg=None):
    from serial_link import StatusDecoder
    decoder=StatusDecoder();deadline=time.monotonic()+seconds
    accepted=False;previous=None;fps=None
    while time.monotonic()<deadline:
        for row in decoder.feed(port.read(64)):
            seq=row['sequence'];frames=row['completed_frames'];now=time.monotonic()
            if previous is None:previous=(frames,now)
            elif now-previous[1]>=.5:
                delta=(frames-previous[0])&0xffffffff
                fps=delta/(now-previous[1]) if delta<0x80000000 else None
                previous=(frames,now)
            print(json.dumps(dict(row,sent_roll_deg=roll_deg,
                                  completed_fps_serial_estimate=fps,
                                  measurement='FPGA processing only; not end-to-end latency')),flush=True)
            if expected_sequence is None or seq==expected_sequence:accepted=True
    return accepted


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--calib',type=Path)
    ap.add_argument('--roll',type=float,default=0)
    ap.add_argument('--yaw',type=float,default=0,help='affine tilt approximation, not perspective homography')
    ap.add_argument('--pitch',type=float,default=0,help='affine tilt approximation')
    ap.add_argument('--zoom',type=float,default=1)
    ap.add_argument('--raw',action='store_true')
    ap.add_argument('--sequence',type=int,default=None)
    ap.add_argument('--out',type=Path,help='offline packet output; no serial device needed')
    ap.add_argument('--port',help='e.g. COM5; requires pyserial')
    ap.add_argument('--watch',type=float,default=3,help='seconds of measured status after sending')
    ap.add_argument('--allow-indirect',action='store_true',help='allow a monitor_rectified indirect estimate')
    ap.add_argument('--allow-synthetic',action='store_true',help='allow synthetic calibration (tool self-test only)')
    ap.add_argument('--allow-phone',action='store_true',help='allow a phone_direct model (not an OV5640 calibration)')
    ap.add_argument('--allow-unverified',action='store_true',help='allow a calibration with no provenance declaration')
    ap.add_argument('--log',type=Path,help='append one JSON line with the sent coefficients and angle')
    args=ap.parse_args()
    if args.sequence is None:args.sequence=secrets.randbelow(255)+1
    if not 1 <= args.sequence <= 255:ap.error('--sequence must be 1..255; 0 is reserved for local mode')
    if not math.isfinite(args.watch) or not 0 < args.watch <= 60:ap.error('--watch must be finite and in (0,60]')
    if not args.calib and not args.raw:ap.error('--calib is required for correction; use --raw for exact identity')
    if not args.out and not args.port:ap.error('specify --out or --port')
    calib=json.loads(args.calib.read_text(encoding='utf-8-sig')) if args.calib else {}
    kind=calib.get('source_kind_operator_declared')
    # Identity mapping needs no optical model; never promote it to a calibration.
    if args.raw:kind='ov5640_raw_digital'
    if kind=='monitor_rectified' and not args.allow_indirect:
        ap.error('this is an indirect phone-screen estimate; pass --allow-indirect to acknowledge its limits')
    if kind=='synthetic' and not args.allow_synthetic:
        ap.error('synthetic calibration is for tool self-test only; pass --allow-synthetic')
    if kind=='phone_direct' and not args.allow_phone:
        ap.error('phone_direct is a phone model, not an OV5640 calibration; pass --allow-phone only for reporting')
    if kind not in ('ov5640_raw_digital','monitor_rectified','synthetic','phone_direct') and not args.allow_unverified:
        ap.error('calibration has no provenance declaration; pass --allow-unverified only if you trust the source')
    coeff=coefficients(calib,args.roll,args.zoom,args.yaw,args.pitch,args.raw)
    from validate_coefficients import validate
    evidence=validate(coeff)
    data=packet(coeff,args.sequence)
    if args.log:
        args.log.parent.mkdir(parents=True,exist_ok=True)
        with args.log.open('a',encoding='utf-8') as f:
            f.write(json.dumps({'time':time.time(),'sequence':args.sequence,'roll_deg':args.roll,
                                'yaw_deg':args.yaw,'pitch_deg':args.pitch,'zoom':args.zoom,
                                'coeff':coeff,'calib_sha256':__import__('hashlib').sha256(args.calib.read_bytes()).hexdigest() if args.calib else None,
                                'measurement':'host command log; confirm with telemetry sequence'})+'\n')
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(data)
        args.out.with_suffix('.json').write_text(json.dumps({'coeff':coeff,'geometry':evidence},indent=2),encoding='utf-8')
        print('Wrote',len(data),'bytes to',args.out)
    if args.port:
        try:import serial
        except ImportError:raise SystemExit('pyserial is missing: run python -m pip install pyserial')
        from serial_link import open_uart
        with open_uart(args.port) as port:
            port.reset_input_buffer();port.write(data);port.flush()
            if not read_status(port,args.watch,args.sequence & 255,args.roll):
                raise SystemExit('No completed frame with the requested sequence received; configuration is unconfirmed')

if __name__=='__main__':main()
