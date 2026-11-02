"""Preview-only orientation must preserve calibration pixels and left/right."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from calibration_console import Console

class PreviewDirection(unittest.TestCase):
    def check_direction(self, flipped):
        # Unequal corner markers detect vertical flip versus 180-degree turn.
        raw=np.array([[[1,2,3],[4,5,6]],[[7,8,9],[10,11,12]],[[13,14,15],[16,17,18]]],dtype=np.uint8)
        original=raw.copy()
        obj=SimpleNamespace(preview_flip_vertical=SimpleNamespace(get=lambda:flipped),draw_previews=Mock(),raw=raw)
        obj.present_preview_image=lambda image:Console.present_preview_image(obj,image)
        Console.show(obj,raw)
        expected=(original[::-1] if flipped else original)[:,:,::-1]
        np.testing.assert_array_equal(np.asarray(obj.preview_source),expected)
        np.testing.assert_array_equal(obj.raw,original)
        obj.draw_previews.assert_called_once()
    def test_vertical_display_only(self):self.check_direction(True)
    def test_default_is_original(self):self.check_direction(False)

if __name__=='__main__':unittest.main()
