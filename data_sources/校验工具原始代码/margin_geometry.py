"""Single geometry identity for sensor firmware, capture and calibration."""
from pathlib import Path
import hashlib,json,zlib
ROOT=Path(__file__).resolve().parents[1]
def load(path=None):
 data=json.loads(Path(path or ROOT/'targets/capture_geometry.json').read_text(encoding='utf-8'))
 return data
def identity(data):
 # Lifecycle declarations do not change physical geometry; all imaging fields do.
 fields={k:v for k,v in data.items() if k not in ('geometry_physically_verified','calibration_required','firmware_role')}
 raw=json.dumps(fields,sort_keys=True,separators=(',',':')).encode('utf-8')
 return hashlib.sha256(raw).hexdigest(),zlib.crc32(raw)&0xffffffff
