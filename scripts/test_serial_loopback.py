"""Exercise isolated loopback transport logic without opening real serial ports."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from serial_loopback import check_echo
class EchoPort:
    def __init__(self,echo=True,partial=False):self.echo=echo;self.partial=partial;self.buffer=bytearray()
    def reset_input_buffer(self):self.buffer.clear()
    def write(self,data):
        n=len(data)-1 if self.partial else len(data)
        if self.echo:self.buffer.extend(data[:n])
        return n
    def flush(self):pass
    @property
    def in_waiting(self):return min(len(self.buffer),3)
    def read(self,n):
        data=bytes(self.buffer[:n]);del self.buffer[:n];return data
class LoopbackTests(unittest.TestCase):
    def test_fragmented_echo(self):
        r=check_echo(EchoPort(),challenge=b'only-test-123\r\n')
        self.assertTrue(r['passed']);self.assertEqual(r['bytes_received'],15)
    def test_no_echo(self):
        r=check_echo(EchoPort(echo=False),timeout_s=.001,challenge=b'hello')
        self.assertFalse(r['passed']);self.assertEqual(r['bytes_received'],0)
    def test_partial_write_is_not_pass(self):
        self.assertFalse(check_echo(EchoPort(partial=True),timeout_s=.001,challenge=b'hello')['passed'])
if __name__=='__main__':unittest.main()
