"""Read-only output-rate acceptance for the 30fps candidate, after manual flash."""
import argparse
import json
from pathlib import Path
from serial_link import open_uart
from uart_acceptance import measure


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    with open_uart(args.port) as port:
        port.reset_input_buffer()
        report=measure(port,15)
    report['port']=args.port
    rate=report['completed_fps_serial_estimate']
    report['uart_link_passed']=report['passed']
    report['rate_target_fps']=[28,32]
    report['rate_target_passed']=report['passed'] and rate is not None and 28<=rate<=32
    report['passed']=report['rate_target_passed']
    report['sensor_SRC_and_PCK_require_screen_confirmation']=True
    report['color_quality_and_tearing_evaluated']=False
    report['note']='UART validates processing completions only. Confirm SRC/PCK, image color and tearing on the monitor; avoid freeze mode.'
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='packets'},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
