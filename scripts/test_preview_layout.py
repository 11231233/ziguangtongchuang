"""Check preview scaling and full-screen lifecycle without camera or UART."""
import json
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from calibration_console import Console

class PreviewLayout(unittest.TestCase):
    def test_fit_large_small_and_portrait(self):
        original=Image.new('RGB',(1280,720))
        for viewport,expected in [((1920,1080),(1920,1080)),((2560,1440),(2560,1440)),((800,600),(800,450)),((1080,1920),(1080,608))]:
            canvas=Mock();canvas.winfo_width.return_value=viewport[0];canvas.winfo_height.return_value=viewport[1]
            app=SimpleNamespace(preview_source=original)
            with patch('calibration_console.ImageTk.PhotoImage',side_effect=lambda image,**kw:image.copy()):
                result=Console.draw_canvas(app,canvas)
            self.assertEqual(result.size,expected)
            self.assertEqual(original.size,(1280,720))
            self.assertLessEqual(result.width,viewport[0]);self.assertLessEqual(result.height,viewport[1])
    def test_hidden_window_lifecycle(self):
        root=tk.Tk();root.withdraw()
        app=Console(root)
        try:
            raw=np.zeros((720,1280,3),dtype=np.uint8);raw[0,0]=[1,2,3]
            app.raw=raw.copy();app.show(raw)
            app.toggle_fullscreen();app.fullscreen_window.withdraw();root.update()
            self.assertIsNotNone(app.fullscreen_window)
            self.assertIsNone(app.cap)
            self.assertIsNone(app.capture_after)
            np.testing.assert_array_equal(app.raw,raw)
            app.close_fullscreen();root.update()
            self.assertIsNone(app.fullscreen_window)
            app.toggle_fullscreen();app.fullscreen_window.withdraw();root.update()
            app.close_fullscreen()
        finally:app.close()

if __name__=='__main__':unittest.main()
