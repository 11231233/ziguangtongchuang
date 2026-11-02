"""Isolated USB-TTL TXD/RXD loopback. Never run while attached to the FPGA."""
import argparse
import datetime
import json
from pathlib import Path
import secrets
import time
from serial_link import open_uart


def check_echo(port, timeout_s=2, challenge=None):
    payload=challenge if challenge is not None else b'CODEX-LOOPBACK-'+secrets.token_hex(16).encode('ascii')+b'\r\n'
    port.reset_input_buffer();port.write_timeout=.5
    written=port.write(payload);port.flush()
    received=bytearray();started=time.monotonic()
    while time.monotonic()-started<timeout_s and len(received)<4096:
        waiting=port.in_waiting
        data=port.read(min(waiting,4096-len(received)) if waiting else 1)
        received.extend(data)
        if payload in received:break
    return dict(passed=written==len(payload) and payload in received,bytes_sent=written,
                expected_bytes=len(payload),bytes_received=len(received),
                full_echo_received=payload in received,received_hex=bytes(received).hex(),
                elapsed_s=time.monotonic()-started,baud=115200,
                scope='isolated USB-TTL TX/RX only; not FPGA-to-PC wiring or firmware validation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--isolated-loopback-confirmed',action='store_true')
    a=p.parse_args()
    if not a.isolated_loopback_confirmed:p.error('disconnect FPGA; connect USB-TTL TXD directly to its own RXD, then confirm isolated loopback')
    if a.out.exists():p.error('output already exists; choose a new file')
    report={'passed':False}
    try:
        with open_uart(a.port,timeout=.02) as port:report=check_echo(port)
    except Exception as exc:report.update(error=str(exc))
    report.update(port=a.port,time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  isolated_loopback_operator_confirmed=True,fpga_connected_operator_declared=False)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    with a.out.open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
