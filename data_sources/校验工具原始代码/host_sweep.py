"""Preflighted affine sweep with bounded steps, deadline pacing and status evidence.
This is host-commanded 2D affine control, not automatic physical-pose estimation.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from host_control import coefficients, packet
from validate_coefficients import validate
from serial_link import StatusDecoder, open_uart


def plan(calib, amplitude=12., hz=.25, duration=8., fps=10., zoom=1., yaw=0., pitch=0., sequence_start=1, max_step=3.):
    values = (amplitude, hz, duration, fps, zoom, yaw, pitch, max_step)
    if not all(math.isfinite(v) for v in values):
        raise ValueError('all sweep inputs must be finite')
    if not (0 <= amplitude <= 45 and hz >= 0 and duration > 0 and 0 < fps <= 30 and zoom > 0 and max_step > 0):
        raise ValueError('invalid amplitude, duration, rate, zoom or step limit')
    if not 1 <= sequence_start <= 255:
        raise ValueError('sequence-start must be 1..255')
    steps = math.ceil(duration * fps)
    if steps + 1 > 255:
        raise ValueError('use at most 255 commands per run for unambiguous sequence acknowledgements')
    result = []
    for i in range(steps + 1):
        t = min(i / fps, duration)
        # Smooth start/end envelope returns exactly to the calibrated zero angle.
        roll = amplitude * math.sin(2 * math.pi * hz * t) * math.sin(math.pi * t / duration)**2
        if i in (0, steps):
            roll = 0.
        if result and abs(roll-result[-1]['roll_deg']) > max_step:
            raise ValueError('angle step exceeds max-step; lower amplitude/frequency or increase command rate')
        seq = ((sequence_start - 1 + i) % 255) + 1
        coeff = coefficients(calib, roll=roll, zoom=zoom, yaw=yaw, pitch=pitch)
        data = packet(coeff, seq)
        geometry = validate(coeff)
        result.append(dict(index=i, t=t, roll_deg=roll, sequence=seq, bytes=len(data),
                           crc16=int.from_bytes(data[-2:], 'big'), geometry=geometry, data=data))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--calib', required=True, type=Path)
    ap.add_argument('--out-dir', type=Path, default=Path('sweep_out'))
    ap.add_argument('--port')
    for name, default in [('amplitude',12.),('hz',.25),('duration',8.),('fps',10.),('zoom',1.),('yaw',0.),('pitch',0.),('max-step',3.)]:
        ap.add_argument('--'+name, type=float, default=default)
    ap.add_argument('--sequence-start', type=int, default=1)
    for name in ('indirect','synthetic','phone','unverified'):
        ap.add_argument('--allow-'+name, action='store_true')
    a = ap.parse_args()
    if a.out_dir.exists():
        ap.error('output directory exists; choose a new run directory')
    raw = a.calib.read_bytes()
    calib = json.loads(raw.decode('utf-8-sig'))
    kind = calib.get('source_kind_operator_declared')
    allowed = {'ov5640_raw_digital': True, 'monitor_rectified': a.allow_indirect,
               'synthetic': a.allow_synthetic, 'phone_direct': a.allow_phone}
    if not allowed.get(kind, a.allow_unverified):
        ap.error('calibration provenance rejected: ' + str(kind))
    # Complete validation before opening UART or creating any partial output.
    trajectory = plan(calib, a.amplitude, a.hz, a.duration, a.fps, a.zoom, a.yaw, a.pitch, a.sequence_start, a.max_step)
    a.out_dir.mkdir(parents=True)
    for row in trajectory:
        (a.out_dir / ('frame_%04d.bin' % row['index'])).write_bytes(row['data'])
    timeline = [{k:v for k,v in row.items() if k != 'data'} for row in trajectory]
    summary = dict(calibration_sha256=hashlib.sha256(raw).hexdigest(), source_kind_operator_declared=kind,
                   packets=len(trajectory), offline_only=not bool(a.port), amplitude_deg=a.amplitude,
                   frequency_hz=a.hz, duration_s=a.duration, command_rate_fps=a.fps,
                   max_step_deg=a.max_step, preflight_all_windows_passed=True,
                   zero_endpoint_planned=True, returned_to_zero_command=False, hardware_tested=False,
                   hardware_dynamic_verified=False, visual_quality_verified=False,
                   note='Frame-boundary affine commands; not IMU or perspective correction. On failure last applied configuration may remain.')
    telemetry, sent, acknowledged = [], set(), set()
    decoder = StatusDecoder()
    port = None
    error = None
    started = time.monotonic()
    def receive():
        data = port.read(1)
        if port.in_waiting:
            data += port.read(min(port.in_waiting, 4096))
        for row in decoder.feed(data):
            row['elapsed_s'] = time.monotonic()-started
            telemetry.append(row)
            if row['sequence'] in sent:
                acknowledged.add(row['sequence'])
    try:
        if a.port:
            port = open_uart(a.port, timeout=.005)
            port.write_timeout = .5
            port.reset_input_buffer()
            started = time.monotonic()
            for row, log in zip(trajectory, timeline):
                deadline = started + row['t']
                while time.monotonic() < deadline:
                    receive()
                if time.monotonic()-deadline > 1/a.fps:
                    raise RuntimeError('host missed a command period; aborting instead of catch-up burst')
                written = port.write(row['data'])
                if written != len(row['data']):
                    raise RuntimeError('short UART write')
                port.flush()
                sent.add(row['sequence'])
                log['sent_elapsed_s'] = time.monotonic()-started
            summary['returned_to_zero_command'] = True
            until = time.monotonic()+3
            while time.monotonic() < until and len(acknowledged) < len(sent):
                receive()
            summary.update(hardware_tested=True, acknowledged_sequences=sorted(acknowledged),
                           sent_commands=len(sent), crc_failures=decoder.crc_failures,
                           version_failures=decoder.version_failures,
                           hardware_dynamic_verified=(len(acknowledged)==len(trajectory) and not decoder.crc_failures and not decoder.version_failures))
            if not summary['hardware_dynamic_verified']:
                raise RuntimeError('not all commands confirmed in completed-frame telemetry')
    except Exception as exc:
        error = str(exc)
        summary['error'] = error
    finally:
        summary.update(sent_commands=len(sent), acknowledged_sequences=sorted(acknowledged),
                       crc_failures=decoder.crc_failures, version_failures=decoder.version_failures)
        if port is not None:
            port.close()
        summary['run_completed'] = error is None
        for filename, value in [('sweep.json',summary), ('timeline.json',timeline), ('telemetry.json',telemetry)]:
            (a.out_dir / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if error else 0

if __name__ == '__main__':
    raise SystemExit(main())
