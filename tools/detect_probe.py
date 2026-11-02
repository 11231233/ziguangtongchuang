import cv2, numpy as np
img = cv2.imread(r"F:\ziguang_jibian\calib\photo_monitor_01.jpg")
print("size", img.shape)
g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
for pat in [(9,6),(8,5),(10,7)]:
    ok, c = cv2.findChessboardCorners(g, pat, cv2.CALIB_CB_ADAPTIVE_THRESH|cv2.CALIB_CB_NORMALIZE_IMAGE|cv2.CALIB_CB_FAST_CHECK)
    print(pat, "found" if ok else "no", (0 if not ok else len(c)))
