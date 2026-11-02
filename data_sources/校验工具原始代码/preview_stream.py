"""Bounded latest-frame workers. No Tk calls and no unbounded video queues."""
from collections import deque
import threading
import time
from preview_denoise import PreviewDenoiser

class LatestCapture:
    def __init__(self, capture):
        self.capture=capture;self._lock=threading.Lock();self._stop=threading.Event()
        self._latest=None;self._sequence=0;self._times=deque(maxlen=120);self.error=None
        self.thread=threading.Thread(target=self._run,daemon=True,name='capture-latest')
        self.thread.start()
    def _run(self):
        try:
            while not self._stop.is_set():
                ok,image=self.capture.read()
                if not ok:
                    self._stop.wait(.01);continue
                now=time.monotonic()
                with self._lock:
                    self._sequence+=1;self._latest=(self._sequence,now,image);self._times.append(now)
        except Exception as exc:self.error=str(exc)
        finally:self.capture.release()
    def latest(self, after_sequence=0):
        with self._lock:
            return self._latest if self._latest and self._latest[0]>after_sequence else None
    def fps(self):
        with self._lock:
            if len(self._times)<2:return 0.
            if time.monotonic()-self._times[-1]>.5:return 0.
            span=self._times[-1]-self._times[0]
            return (len(self._times)-1)/span if span>0 else 0.
    def stop(self, timeout=.2):
        self._stop.set();self.thread.join(timeout)
        return not self.thread.is_alive()

class LatestPreviewFilter:
    def __init__(self, processor=None):
        self.processor=processor or PreviewDenoiser();self._condition=threading.Condition()
        self._pending=None;self._result=None;self._epoch=0;self._job=0;self._stopped=False
        self.error=None;self.skipped=0
        self.thread=threading.Thread(target=self._run,daemon=True,name='preview-filter-latest')
        self.thread.start()
    def invalidate(self):
        with self._condition:
            self._epoch+=1;self._pending=None;self._result=None;self.error=None
    def submit(self, image, mode, metadata):
        with self._condition:
            if self._stopped:return
            self._job+=1
            if self._pending is not None:self.skipped+=1
            self._pending=(self._epoch,self._job,image,mode,dict(metadata))
            self._condition.notify()
    def latest(self, after_job=0):
        with self._condition:
            if self._result and self._result['job']>after_job:return self._result
            return None
    def _run(self):
        epoch=None
        while True:
            with self._condition:
                self._condition.wait_for(lambda:self._stopped or self._pending is not None)
                if self._stopped:return
                request=self._pending;self._pending=None
            generation,job,image,mode,metadata=request
            try:
                if generation!=epoch:self.processor.reset();epoch=generation
                started=time.monotonic()
                output=self.processor.process(image,mode,use_temporal=True)
                elapsed=(time.monotonic()-started)*1000
                result=dict(job=job,original=image,output=output,mode=mode,metadata=metadata,
                            processing_ms=elapsed,replaced_pixels=self.processor.corrected_pixels)
                with self._condition:
                    if generation==self._epoch:self._result=result
            except Exception as exc:
                with self._condition:
                    if generation==self._epoch:self.error=str(exc)
    def close(self, timeout=.2):
        with self._condition:
            self._stopped=True;self._pending=None;self._condition.notify_all()
        self.thread.join(timeout)
        return not self.thread.is_alive()
