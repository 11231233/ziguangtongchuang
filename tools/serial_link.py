"""Shared 115200/8N1 transport and incremental FPGA telemetry decoder."""
import binascii
import struct


def open_uart(name, timeout=.1):
    import serial
    from serial.tools import list_ports
    selected = next((p for p in list_ports.comports() if p.device.upper() == name.upper()), None)
    if selected and (selected.vid, selected.pid) == (0x0403, 0x6010):
        raise ValueError('FTDI downloader port is not the verified USB-TTL interface')
    port = serial.Serial(port=None, baudrate=115200, timeout=timeout,
                         bytesize=8, parity='N', stopbits=1,
                         xonxoff=False, rtscts=False, dsrdtr=False)
    port.dtr = False
    port.rts = False
    port.port = name
    try:
        port.open()
    except Exception:
        port.close()
        raise
    return port


class StatusDecoder:
    def __init__(self):
        self.buffer = bytearray()
        self.crc_failures = 0
        self.version_failures = 0

    def feed(self, data):
        self.buffer.extend(data)
        records = []
        while len(self.buffer) >= 2:
            pos = self.buffer.find(b'\xa5\x5b')
            if pos < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer[-1] == 0xa5 else b''
                break
            if pos:
                del self.buffer[:pos]
            if len(self.buffer) < 14:
                break
            record = bytes(self.buffer[:14])
            if binascii.crc_hqx(record[2:12], 0xffff) != int.from_bytes(record[12:], 'big'):
                self.crc_failures += 1
                del self.buffer[0]
                continue
            if record[2] != 1:
                self.version_failures += 1
                del self.buffer[0]
                continue
            _, seq, cycles, frames = struct.unpack('<BBII', record[2:12])
            records.append(dict(sequence=seq, process_cycles=cycles,
                                process_ms=cycles / 100000, completed_frames=frames))
            del self.buffer[:14]
        return records
