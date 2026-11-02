"""Alternative stateless filters: interpolation spots, texture and motion."""
import sys
import unittest
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from preview_denoise import repair_small_spots,suppress_impulses,gentle_bilateral,PreviewDenoiser

class AlternativeFilters(unittest.TestCase):
    def test_small_clusters_removed_while_old_single_pixel_detector_misses(self):
        frame=np.full((64,64,3),80,np.uint8)
        frame[10:12,10:12]=255;frame[30:33,30:33]=0
        original=frame.copy()
        old,old_mask=suppress_impulses(frame)
        new,mask=repair_small_spots(frame)
        self.assertFalse(old_mask.any())
        self.assertEqual(mask.sum(),13)
        np.testing.assert_array_equal(new,np.full_like(frame,80))
        np.testing.assert_array_equal(frame,original)
    def test_bilinear_spread_hot_pixel(self):
        source=np.full((64,64,3),20,np.uint8);source[30,30]=255
        frame=cv2.warpAffine(source,np.array([[1,0,.5],[0,1,.5]],np.float32),(64,64),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        old,old_mask=suppress_impulses(frame)
        new,mask=repair_small_spots(frame)
        self.assertFalse(old_mask.any());self.assertEqual(mask.sum(),4)
        self.assertTrue(np.all(new==20))
    def test_long_lines_and_borders_preserved(self):
        frame=np.full((64,64,3),80,np.uint8);frame[:,20]=255;frame[30,:]=0;frame[0,0]=255
        new,mask=repair_small_spots(frame)
        np.testing.assert_array_equal(new,frame);self.assertFalse(mask.any())
    def test_texture_guard_bypasses_dense_pattern(self):
        yy,xx=np.indices((64,64));gray=((xx+yy)%2*255).astype(np.uint8)
        frame=np.repeat(gray[:,:,None],3,axis=2)
        new,mask=repair_small_spots(frame)
        np.testing.assert_array_equal(new,frame);self.assertFalse(mask.any())
    def test_stateless_replacement_has_no_moving_spot_trail(self):
        p=PreviewDenoiser();first=np.full((64,64,3),80,np.uint8);first[10:12,10:12]=255
        second=np.full_like(first,80);second[40:42,40:42]=255
        for frame in (first,second):self.assertTrue(np.all(p.process(frame,'small_spots')==80))
        self.assertIsNone(p.previous)
    def test_moving_real_large_object_preserved(self):
        p=PreviewDenoiser()
        for x in (10,25):
            frame=np.full((64,64,3),80,np.uint8);frame[20:30,x:x+10]=220
            np.testing.assert_array_equal(p.process(frame,'small_spots'),frame)
    def test_bilateral_flat_noise_reduced_and_edge_contrast_retained(self):
        rng=np.random.default_rng(8);clean=np.full((64,64,3),80,np.uint8);clean[:,32:]=180
        noisy=np.clip(np.rint(clean+rng.normal(0,3,clean.shape)),0,255).astype(np.uint8)
        original=noisy.copy();out=gentle_bilateral(noisy)
        self.assertLess(np.mean((out[:,:25].astype(float)-80)**2),np.mean((noisy[:,:25].astype(float)-80)**2))
        self.assertGreater(float(out[:,35:].mean()-out[:,:29].mean()),95)
        np.testing.assert_array_equal(noisy,original)
    def test_genuine_small_feature_can_still_be_deleted(self):
        frame=np.zeros((32,32,3),np.uint8);frame[15:17,15:17]=255
        output,mask=repair_small_spots(frame)
        self.assertEqual(mask.sum(),4)
    def test_invalid_thresholds_rejected(self):
        frame=np.zeros((16,16,3),np.uint8)
        with self.assertRaises(ValueError):repair_small_spots(frame,threshold=0)

    def test_many_components_vectorized_path_preserves_line(self):
        clean=np.full((96,96,3),80,np.uint8);clean[:,90]=220
        frame=clean.copy()
        for index in range(20):
            y=8+(index//8)*16;x=8+(index%8)*10
            frame[y:y+2,x:x+2]=255
        output,mask=repair_small_spots(frame)
        self.assertEqual(mask.sum(),80)
        np.testing.assert_array_equal(output,clean)

if __name__=='__main__':unittest.main()
