"""List serial ports, or explicitly read FPGA status without sending commands."""
import argparse
import sys
from host_control import read_status

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true',help='enumerate ports only; open none')
    parser.add_argument('--port',help='explicit USB-TTL port, for example COM5')
    parser.add_argument('--seconds',type=float,default=5)
    args=parser.parse_args()
    if not 0 < args.seconds <= 60:parser.error('--seconds must be greater than 0 and at most 60')
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        parser.error('Install pyserial: python -m pip install pyserial')
    ports=list(list_ports.comports())
    if args.list or not args.port:
        for item in ports:
            label=' [FTDI dual-channel device: existing downloader is not a verified UART]' if (item.vid,item.pid)==(0x0403,0x6010) else ''
            print(f'{item.device}: {item.description} VID={item.vid} PID={item.pid}{label}')
        if not ports:print('No serial ports found')
        return 0
    selected=next((item for item in ports if item.device.upper()==args.port.upper()),None)
    if selected and (selected.vid,selected.pid)==(0x0403,0x6010):
        parser.error('This is an unverified FTDI dual-channel/downloader port. Select the separately connected USB-TTL adapter.')
    # Configure handshake lines before opening. No image/parameter bytes are sent.
    port=serial.Serial(port=None,baudrate=115200,timeout=.1)
    port.dtr=False;port.rts=False;port.port=args.port
    try:
        port.open()
        ok=read_status(port,args.seconds)
    finally:
        port.close()
    if not ok:
        print('No valid FPGA status packet. Check TX/RX, GND, adapter port, and that video processing is running.',file=sys.stderr)
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
