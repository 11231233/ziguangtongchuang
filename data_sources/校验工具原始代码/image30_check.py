"""Read-only 60-second output completion-rate check; image quality needs visual review."""
import argparse
import json
import statistics
import datetime
from pathlib import Path
from serial_link import open_uart
from uart_acceptance import measure


def assess(report):
    rows = report['packets']
    rate = report['completed_fps_serial_estimate']
    windows = []
    anchor = rows[0] if rows else None
    for row in rows[1:]:
        span = row['elapsed_s'] - anchor['elapsed_s']
        if span >= 5:
            count = (row['completed_frames'] - anchor['completed_frames']) & 0xffffffff
            windows.append(dict(start_s=anchor['elapsed_s'], seconds=span,
                                fps=count / span if count < 0x80000000 else None))
            anchor = row
    max_gap = max((b['elapsed_s'] - a['elapsed_s'] for a, b in zip(rows, rows[1:])), default=None)
    duration = rows[-1]['elapsed_s'] - rows[0]['elapsed_s'] if len(rows) > 1 else 0
    # Include a trailing loss of telemetry (e.g. power/clock loss), not just gaps
    # between packets that arrived. PC scheduling/USB stalls can also fail this.
    tail_gap = max(0, report.get('requested_seconds', 60) - rows[-1]['elapsed_s']) if rows else None
    link = bool(report['passed'] and not report['version_failures'])
    average_ok = bool(rate is not None and 29.5 <= rate <= 30.5)
    windows_ok = len(windows) >= 10 and all(w['fps'] is not None and 29 <= w['fps'] <= 31 for w in windows)
    continuity_ok = bool(duration >= 55 and max_gap is not None and max_gap <= .5 and tail_gap <= .5)
    values = sorted(r['process_ms'] for r in rows)
    batched = report.get('max_packets_per_receive_batch', 1) > 1 or any(
        b['elapsed_s'] == a['elapsed_s'] for a, b in zip(rows, rows[1:]))
    return dict(uart_link_passed=link, average_target_fps=[29.5, 30.5],
                window_target_fps=[29, 31], windows=windows,
                observed_packet_gap_max_s=max_gap, trailing_gap_s=tail_gap,
                observed_span_s=duration,
                process_ms_p95=values[min(len(values)-1, int(len(values)*.95))] if values else None,
                average_rate_passed=average_ok, window_rates_passed=windows_ok,
                telemetry_continuity_passed=continuity_ok,
                receive_batching_detected=batched,
                hardware_frame_jitter_verified=False,
                competition_acceptance_pass=None,
                passed=link and average_ok and windows_ok and continuity_ok,
                image_quality_verified=False, hardware_input_pclk_measured=False,
                note='Completion rate only. H0 live mode required. Inspect PCK/SRC and sparkles/tearing separately; USB/PC stalls can affect timestamp continuity.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM24')
    parser.add_argument('--out', type=Path, default=None)
    args = parser.parse_args()
    if args.out is None:
        args.out = Path(__file__).resolve().parents[1] / 'reports' / ('board_60s_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.json')
    if args.out.exists():
        parser.error('output exists; choose a new file to preserve prior measurements')
    with open_uart(args.port, timeout=.02) as port:
        port.reset_input_buffer()
        report = measure(port, 60)
    report.update(port=args.port, requested_seconds=60)
    report.update(assess(report))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2))
    print('Saved:', args.out)
    print(json.dumps({k:v for k,v in report.items() if k not in ['packets','windows']}, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
