"""Read-only UART measurement. Does not send parameters or open video devices."""
import argparse
import datetime
import json
import math
from pathlib import Path
import statistics
import time

from serial_link import StatusDecoder, open_uart


def measure(port, seconds):
    if not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise ValueError('seconds must be finite and in (0,60]')
    decoder = StatusDecoder()
    start = time.monotonic()
    rows = []
    received = 0
    batches = []
    while time.monotonic() - start < seconds:
        # Block for one byte, then drain bytes already available. A fixed
        # 256-byte read waits for ~18 status packets before timestamping them.
        data = port.read(1)
        waiting = port.in_waiting
        if waiting:
            data += port.read(min(waiting, 4096))
        received += len(data)
        now = time.monotonic()
        decoded = decoder.feed(data)
        if decoded:
            batches.append(len(decoded))
        for row in decoded:
            rows.append(dict(row, elapsed_s=now - start, receive_batch_packets=len(decoded)))
    advancing = 0
    discontinuities = 0
    for a, b in zip(rows, rows[1:]):
        delta = (b['completed_frames'] - a['completed_frames']) & 0xffffffff
        if 0 < delta < 0x80000000:
            advancing += delta
        if delta != 1:
            discontinuities += 1
    span = rows[-1]['elapsed_s'] - rows[0]['elapsed_s'] if len(rows) > 1 else 0
    ms = [r['process_ms'] for r in rows]
    result = dict(time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
                  baud=115200, bytes_received=received, valid_packets=len(rows),
                  crc_failures=decoder.crc_failures, version_failures=decoder.version_failures,
                  frame_counter_discontinuities=discontinuities,
                  sequence_values=sorted({r['sequence'] for r in rows}),
                  process_ms_min=min(ms) if ms else None,
                  process_ms_median=statistics.median(ms) if ms else None,
                  process_ms_max=max(ms) if ms else None,
                  completed_fps_serial_estimate=advancing / span if span and not discontinuities else None,
                  passed=len(rows) >= 2 and advancing > 0 and not discontinuities and decoder.crc_failures == 0 and decoder.version_failures == 0,
                  receiver_version='byte_drain_v2',
                  timestamp_source='host_monotonic_after_read_not_hardware',
                  max_packets_per_receive_batch=max(batches, default=0),
                  batched_packet_count=sum(n for n in batches if n > 1),
                  parameters_sent=False, video_devices_opened=False,
                  measurement_scope='FPGA processing time and completed frames; not end-to-end latency or HDMI refresh',
                  packets=rows)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('output exists; choose a new file to preserve prior measurements')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 60:
        parser.error('seconds must be finite and in (0,60]')
    with open_uart(args.port, timeout=.02) as port:
        port.reset_input_buffer()
        result = measure(port, args.seconds)
    result['port'] = args.port
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != 'packets'}, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
