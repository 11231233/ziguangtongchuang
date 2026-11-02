"""Bounded, read-only alternative RX audit. No camera or FPGA control writes."""
import argparse,collections,ctypes,datetime,json,statistics,time
from pathlib import Path
from serial_link import open_uart,StatusDecoder

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',required=True)
    ap.add_argument('--seconds',type=float,default=5)
    args=ap.parse_args()
    if not .1<=args.seconds<=10:raise SystemExit('seconds must be .1..10')
    p=Path(__file__).resolve().parents[1]/'reports'/datetime.datetime.now().strftime('uart_bulk_%Y%m%d_%H%M%S_%f')
    p.mkdir()
    counts=collections.Counter();original=None;win32=None
    import os
    if os.name=='nt':
        from serial import win32
        original=win32.ClearCommError
        def observe(handle,errors,status):
            ok=original(handle,errors,status)
            if ok:
                mask=ctypes.cast(errors,ctypes.POINTER(win32.DWORD)).contents.value
                if mask:counts[mask]+=1
            return ok
        win32.ClearCommError=observe
    raw=bytearray();rows=[];decoder=StatusDecoder()
    result={'parameters_sent':False,'video_devices_opened':False,'port':args.port,
            'baud':115200,'requested_seconds':args.seconds,'receiver':'bulk4096_timeout20ms',
            'timestamp_source':'host_after_bulk_read_not_hardware'}
    try:
        with open_uart(args.port,timeout=.02) as port:
            port.reset_input_buffer();counts.clear();start=time.monotonic()
            while time.monotonic()-start<args.seconds:
                data=port.read(4096);raw.extend(data);now=time.monotonic()-start
                decoded=decoder.feed(data)
                rows.extend(dict(x,elapsed_s=now,receive_batch_packets=len(decoded)) for x in decoded)
            result['observed_read_seconds']=time.monotonic()-start
    except Exception as exc:result['error']=str(exc)
    finally:
        if original:win32.ClearCommError=original
    deltas=[(b['completed_frames']-a['completed_frames'])&0xffffffff for a,b in zip(rows,rows[1:])]
    span=rows[-1]['elapsed_s']-rows[0]['elapsed_s'] if len(rows)>1 else 0
    discontinuities=sum(x!=1 for x in deltas)
    result.update(time=datetime.datetime.now().astimezone().isoformat(),bytes_received=len(raw),
        valid_packets=len(rows),crc_failures=decoder.crc_failures,version_failures=decoder.version_failures,
        frame_counter_discontinuities=discontinuities,windows_error_masks=dict(counts),
        completed_fps_serial_estimate=(sum(deltas)/span if span and not discontinuities else None),
        process_ms_median=statistics.median([x['process_ms'] for x in rows]) if rows else None,
        max_packets_per_batch=max([x['receive_batch_packets'] for x in rows],default=0),packets=rows)
    (p/'received.bin').write_bytes(raw)
    (p/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='packets'},ensure_ascii=False,indent=2))
    print('REPORT '+str(p))
    return int('error' in result)

if __name__=='__main__':raise SystemExit(main())
