"""Read-only paired comparison of the existing one-byte drain and bulk RX."""
import argparse,datetime,json,time
from pathlib import Path
from serial_link import open_uart,StatusDecoder
from uart_acceptance import measure

def bulk_measure(port,seconds):
    decoder=StatusDecoder();rows=[];received=0;start=time.monotonic()
    while time.monotonic()-start<seconds:
        data=port.read(4096);received+=len(data);now=time.monotonic()-start
        decoded=decoder.feed(data)
        rows.extend(dict(row,elapsed_s=now,receive_batch_packets=len(decoded)) for row in decoded)
    deltas=[(b['completed_frames']-a['completed_frames'])&0xffffffff for a,b in zip(rows,rows[1:])]
    span=rows[-1]['elapsed_s']-rows[0]['elapsed_s'] if len(rows)>1 else 0
    discontinuities=sum(n!=1 for n in deltas)
    return dict(bytes_received=received,valid_packets=len(rows),crc_failures=decoder.crc_failures,
        version_failures=decoder.version_failures,frame_counter_discontinuities=discontinuities,
        completed_fps_serial_estimate=sum(deltas)/span if span and not discontinuities else None,
        packets=rows)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--port',required=True)
    ap.add_argument('--seconds',type=float,default=5);args=ap.parse_args()
    if not .1<=args.seconds<=10:raise SystemExit('seconds must be .1..10')
    folder=Path(__file__).resolve().parents[1]/'reports'/datetime.datetime.now().strftime('uart_reader_comparison_%Y%m%d_%H%M%S_%f')
    folder.mkdir();results=[]
    for mode in ['existing_one_byte_A1','bulk4096_B','existing_one_byte_A2']:
        with open_uart(args.port,timeout=.02) as port:
            port.reset_input_buffer()
            report=(bulk_measure if mode=='bulk4096_B' else measure)(port,args.seconds)
            # Exposes any application-visible backlog without deleting it first.
            report['queue_bytes_at_end']=port.in_waiting
        report.update(mode=mode,port=args.port,parameters_sent=False)
        (folder/(mode+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        summary={k:v for k,v in report.items() if k!='packets'}
        rows=report['packets']
        if rows:summary.update(first=rows[0],last=rows[-1])
        results.append(summary);print(json.dumps(summary),flush=True)
    (folder/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('REPORT '+str(folder),flush=True)

if __name__=='__main__':main()
