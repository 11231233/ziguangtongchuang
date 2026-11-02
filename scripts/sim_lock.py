"""Prevent concurrent workflows from overwriting shared sim/out vectors."""
import atexit
import os
from pathlib import Path

def release(handle):
    if handle.closed:return
    handle.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_UN)
    handle.close()

def acquire(root):
    folder=Path(root)/'sim';folder.mkdir(exist_ok=True,parents=True)
    handle=(folder/'.vectors.lock').open('a+b')
    handle.seek(0,2)
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit('Another simulation workflow owns sim/out. Run these workflows sequentially or in separate project copies.')
    atexit.register(release,handle)
    return handle
