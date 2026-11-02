"""Create the console without opening capture/serial devices, then exit."""
from pathlib import Path
import argparse
import json
import sys
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path, default=ROOT / 'reports/revision5/gui_smoke.json')
args = parser.parse_args()
sys.path.insert(0, str(ROOT / 'tools'))
from calibration_console import Console
import calibration_workflow as flow

root = tk.Tk()
root.withdraw()
app = Console(root)
root.update()
assert app.cap is None and app.model is None and not app.wired.get()
app.list_ports()  # Inventory only, never opens any COM device.
app.set_model(ROOT / 'calib/ov5640_indirect_single_01.json')
rejected = False
try:
    app.real_model()
except ValueError:
    rejected = True
assert rejected, 'Indirect model must not be offered as measured calibration'
assert app.cap is None and app.capture_after is None
app.model = None; app.model_path = None
root.update_idletasks()
checks = {'passed': True, 'hardware_devices_opened': False,
    'checks': ['widget construction', 'disconnected startup', 'COM inventory without connection',
               'indirect calibration export rejected', 'capture timer remains stopped'],
    'default_max_window_size': [1180, 900],
    'layout_requested_size': [root.winfo_reqwidth(), root.winfo_reqheight()]}
out = args.out
out.parent.mkdir(parents=True, exist_ok=True)
flow.write_json(out, checks)
print(json.dumps(checks, indent=2))
app.close()
