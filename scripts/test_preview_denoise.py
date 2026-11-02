"""Independent noise/motion/impulse tests, not real camera acceptance."""
import json
import sys
import time
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock,patch
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from preview_denoise import suppress_impulses,temporal_step,PreviewDenoiser

class DenoiseTests(unittest.TestCase):
    def test_isolated_white_black_and_colored_outliers(self):
        image=np.full((32,32,3),100,np.uint8)
        image[8,8]=255;image[15,15]=0;image[23,23]=[100,255,100]
        source=image.copy();result,mask=suppress_impulses(image)
        self.assertEqual(int(mask.sum()),3)
        for y,x in [(8,8),(15,15),(23,23)]:np.testing.assert_array_equal(result[y,x],[100]*3)
        np.testing.assert_array_equal(image,source)
    def test_edges_lines_and_borders_retained(self):
        image=np.full((32,32,3),60,np.uint8);image[:,16:]=180
        image[:,5]=255;image[0,0]=255
        result,mask=suppress_impulses(image)
        np.testing.assert_array_equal(result,image);self.assertEqual(int(mask.sum()),0)
    def test_real_isolated_detail_is_ambiguous(self):
        image=np.zeros((9,9,3),np.uint8);image[4,4]=255
        result,mask=suppress_impulses(image)
        self.assertTrue(mask[4,4]);self.assertTrue(np.all(result[4,4]==0))
    def test_explicit_defect_map_only_changes_marked_pixels(self):
        image=np.full((16,16,3),90,np.uint8);image[5,5]=255;image[10,10]=255
        mask=np.zeros((16,16),bool);mask[5,5]=True
        result,_=suppress_impulses(image,defect_mask=mask)
        self.assertTrue(np.all(result[5,5]==90));self.assertTrue(np.all(result[10,10]==255))
    def test_full_range_first_frame_and_motion_bypass(self):
        rng=np.random.default_rng(1)
        x=rng.integers(0,256,(30,40,3),np.uint8)
        np.testing.assert_array_equal(temporal_step(x,None),x)
        dark=np.zeros((30,40,3),np.uint8);bright=np.full_like(dark,255)
        np.testing.assert_array_equal(temporal_step(bright,dark),bright)
        np.testing.assert_array_equal(temporal_step(dark,bright),dark)
    def test_repeated_render_is_not_another_noise_sample(self):
        p=PreviewDenoiser();first=np.full((8,8,3),100,np.uint8);second=np.full_like(first,112)
        p.process(first,'temporal');a=p.process(second,'temporal').copy()
        for _ in range(10):np.testing.assert_array_equal(p.process(second,'temporal'),a)
        self.assertTrue(np.any(p.process(second.copy(),'temporal')!=a))
    def test_mode_reset_and_still_frame_bypass(self):
        p=PreviewDenoiser();p.process(np.zeros((8,8,3),np.uint8),'temporal')
        frame=np.full((8,8,3),12,np.uint8)
        np.testing.assert_array_equal(p.process(frame,'off'),frame)
        np.testing.assert_array_equal(p.process(frame.copy(),'temporal'),frame)
        np.testing.assert_array_equal(p.process(frame.copy(),'temporal',use_temporal=False),frame)
    def test_independent_temporal_noise_reduces_flat_region_error(self):
        rng=np.random.default_rng(4);p=PreviewDenoiser();raw=[];filtered=[]
        for i in range(64):
            image=np.clip(np.rint(128+rng.normal(0,4,(96,128,3))),0,255).astype(np.uint8)
            out=p.process(image,'temporal')
            if i>=16:raw.append(image.astype(float)-128);filtered.append(out.astype(float)-128)
        original=np.stack(raw);result=np.stack(filtered)
        self.assertLess(np.mean(result**2),np.mean(original**2)*.6)
    def test_invalid_inputs(self):
        for image in [np.zeros((4,4),np.uint8),np.zeros((4,4,3),float)]:
            with self.assertRaises(ValueError):suppress_impulses(image)
        with self.assertRaises(ValueError):temporal_step(np.zeros((4,4,3),np.uint8),None,motion_threshold=0)

    def test_gui_denoises_preview_but_saves_original_png(self):
        import cv2
        from calibration_console import Console
        raw=np.full((32,32,3),100,np.uint8);raw[8,8]=255
        original=raw.copy()
        variable=lambda value:SimpleNamespace(get=lambda:value)
        app=SimpleNamespace(preview_denoiser=PreviewDenoiser(),denoise_mode=variable('孤立光点抑制'),
            cap=Mock(),raw=raw,raw_source='synthetic_test',capture_flip_vertical=variable(False),
            preview_mode=variable('原始输入'),preview_flip_vertical=variable(False),draw_previews=Mock())
        app.present_preview_image=lambda image:Console.present_preview_image(app,image)
        Console.show(app,raw)
        np.testing.assert_array_equal(app.raw,original)
        self.assertTrue(np.all(app.denoise_output[8,8]==100))
        self.assertTrue(np.all(app.denoise_input[8,8]==255))
        app.guarded=lambda fn:fn();app.job=lambda fn:fn()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'raw.png'
            with patch('calibration_console.filedialog.asksaveasfilename',return_value=str(path)):
                Console.save_digital_frame(app)
            saved=cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
            np.testing.assert_array_equal(saved,original)
            metadata=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertFalse(metadata['pc_preview_denoise_applied_to_saved_file'])

if __name__=='__main__':unittest.main()
