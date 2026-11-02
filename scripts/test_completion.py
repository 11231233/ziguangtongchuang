"""Offline regression for RAW export and resilient telemetry parsing."""
from pathlib import Path
import binascii
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from serial_link import StatusDecoder
from host_control import coefficients
from inspect_sampling_geometry import mapping


def status(seq=83, frames=1, version=1):
    body = struct.pack('<BBII', version, seq, 2950727, frames)
    return b'\xa5\x5b' + body + struct.pack('>H', binascii.crc_hqx(body, 0xffff))


class CompletionTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'tools/host_control.py'), *map(str,args)],
                              capture_output=True, text=True)

    def test_raw_without_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'raw.bin'
            run = self.cli('--raw', '--out', out, '--sequence', 5)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            packet = out.read_bytes()
            self.assertEqual(len(packet), 62)
            self.assertEqual(binascii.crc_hqx(packet[2:-2], 0xffff), int.from_bytes(packet[-2:], 'big'))
            report = json.loads(out.with_suffix('.json').read_text())
            self.assertEqual(report['geometry']['valid_pixels'], 921600)
            self.assertEqual(report['geometry']['window_misses'], 0)

    def test_identity_all_720p_coordinates(self):
        x,y = np.meshgrid(np.arange(1280,dtype=np.int64), np.arange(720,dtype=np.int64))
        u,v = mapping(coefficients({},raw=True),x,y)
        np.testing.assert_array_equal(u,x*65536)
        np.testing.assert_array_equal(v,y*65536)

    def test_packet_resynchronization(self):
        decoder = StatusDecoder()
        corrupt = bytearray(status()); corrupt[5] ^= 8
        stream = b'noise\xa5' + bytes(corrupt) + status(version=2) + status(frames=0xffffffff) + status(frames=0)
        found=[]
        for byte in stream:found.extend(decoder.feed(bytes([byte])))
        self.assertEqual([r['completed_frames'] for r in found], [0xffffffff,0])
        self.assertEqual(decoder.crc_failures,1)
        self.assertEqual(decoder.version_failures,1)
        self.assertAlmostEqual(found[0]['process_ms'],29.50727)

    def test_invalid_sequence_watch_and_unverified_model(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'bad.bin'
            for seq in ('0','256','-1'):
                self.assertNotEqual(self.cli('--raw','--sequence',seq,'--out',out).returncode,0)
            for watch in ('nan','inf','0','61'):
                self.assertNotEqual(self.cli('--raw','--watch',watch,'--out',out).returncode,0)
            self.assertFalse(out.exists())
            model=Path(folder)/'unverified.json';model.write_text('{}')
            self.assertNotEqual(self.cli('--calib',model,'--out',out).returncode,0)
            self.assertFalse(out.exists())


if __name__ == '__main__':unittest.main()
