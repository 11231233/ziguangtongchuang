"""Tests of receive timing and dynamic-command preflight; synthetic only."""
import binascii
import math
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from uart_acceptance import measure
from host_sweep import plan

class Clock:
    now = 0.
    def monotonic(self): return self.now

class Port:
    def __init__(self, clock, frames=(1,2,3), version=1):
        self.clock=clock
        self.frames=iter(frames)
        self.pending=b''
        self.version=version
        self.requests=[]
    @property
    def in_waiting(self): return len(self.pending)
    def read(self,n):
        self.requests.append(n)
        if self.pending:
            value,self.pending=self.pending[:n],self.pending[n:]
            return value
        self.clock.now += .034
        try: frame=next(self.frames)
        except StopIteration: return b''
        body=struct.pack('<BBII',self.version,7,2800000,frame)
        data=b'\xa5\x5b'+body+binascii.crc_hqx(body,0xffff).to_bytes(2,'big')
        self.pending=data[1:]
        return data[:1]

class Measurements(unittest.TestCase):
    def run_port(self, frames=(1,2,3),version=1):
        c=Clock();p=Port(c,frames,version)
        with patch('uart_acceptance.time.monotonic',c.monotonic): r=measure(p,.15)
        return r,p
    def test_byte_drain(self):
        r,p=self.run_port()
        self.assertTrue(r['passed'])
        self.assertEqual(p.requests[:2],[1,13])
        self.assertEqual(r['max_packets_per_receive_batch'],1)
        self.assertAlmostEqual(r['completed_fps_serial_estimate'],1/.034)
        self.assertEqual(len(set(x['elapsed_s'] for x in r['packets'])),3)
    def test_skip_duplicate_reset_and_wrap(self):
        for frames in [(1,3,4),(1,1,2),(10,0,1)]:
            r,_=self.run_port(frames)
            self.assertFalse(r['passed'])
            self.assertGreater(r['frame_counter_discontinuities'],0)
        self.assertTrue(self.run_port((0xfffffffe,0xffffffff,0))[0]['passed'])
    def test_version_rejected(self):
        r,_=self.run_port(version=2)
        self.assertFalse(r['passed']);self.assertEqual(r['version_failures'],3)
    def test_duration(self):
        for value in (0,-1,float('nan'),float('inf'),61):
            with self.assertRaises(ValueError): measure(None,value)

class Sweep(unittest.TestCase):
    model=dict(fx=520.,fy=520.,cx=640.,cy=360.,k1=0.,k2=0.,p1=0.,p2=0.,k3=0.,image_size=[1280,720])
    def test_window_validation_and_return(self):
        trajectory=plan(self.model,duration=.3,fps=10,sequence_start=254)
        self.assertEqual([r['sequence'] for r in trajectory],[254,255,1,2])
        self.assertEqual(trajectory[0]['roll_deg'],0)
        self.assertEqual(trajectory[-1]['roll_deg'],0)
        self.assertTrue(all(r['geometry']['window_misses']==0 for r in trajectory))
    def test_bad_inputs(self):
        for kw in [dict(fps=31),dict(duration=26),dict(hz=math.nan),dict(zoom=0),dict(sequence_start=0),dict(max_step=0)]:
            with self.assertRaises(ValueError): plan(self.model,**kw)
    def test_jump_rejected(self):
        with self.assertRaisesRegex(ValueError,'angle step'):
            plan(self.model,duration=1,amplitude=45,hz=1,fps=4,max_step=.1)
    def test_unfetchable_before_uart(self):
        with self.assertRaises(ValueError): plan(dict(self.model,fx=.01),duration=.1)

if __name__=='__main__': unittest.main()
