"""Read-only output-rate report for the 76.8MHz camera candidate."""
import argparse,json
from pathlib import Path
from serial_link import open_uart
from uart_acceptance import measure

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    with open_uart(args.port) as port:
        port.reset_input_buffer();report=measure(port,15)
    report['port']=args.port
    rate=report['completed_fps_serial_estimate']
    report['uart_link_passed']=report['passed']
    report['rate_target_fps']=[25,29]
    report['rate_target_passed']=report['passed'] and rate is not None and 25<=rate<=29
    report['passed']=report['rate_target_passed']
    report['color_sparkles_and_tearing_evaluated']=False
    report['note']='Processing completion rate only; confirm H0 live mode, camera PCK/SRC and image integrity separately.'
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='packets'},ensure_ascii=False,indent=2))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
