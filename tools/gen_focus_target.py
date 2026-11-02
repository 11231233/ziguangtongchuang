"""Deterministic printable focus aid, not a certified SFR/MTF or calibration target."""
from pathlib import Path
from math import sin, cos, radians
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
dpi = 300
scale = dpi / 25.4
def px(mm): return round(mm * scale)
image = Image.new('L', (px(297), px(210)), 255)
draw = ImageDraw.Draw(image)
font_path = Path('C:/Windows/Fonts/msyh.ttc')
def text(x, y, value, points=11):
    font = ImageFont.truetype(str(font_path), round(points * dpi / 72))
    draw.text((px(x), px(y)), value, font=font, fill=0)

draw.rectangle((px(8), px(8), px(289), px(202)), outline=0, width=px(.2))
text(14, 12, '对焦与清晰度辅助卡', 20)
text(14, 25, 'A4 横向 / 100% 实际大小 / 贴平固定 / 摄像头与光照保持不变', 10)
text(14, 32, '先在 RAW 原图调清楚，再切回 COR；FOC 仅作同一场景内的相对参考。', 10)

# Several known line-pair spacings help visually detect focus loss.
for i, freq in enumerate([.25, .5, 1., 2., 3.]):
    x0 = 16 + i * 55
    text(x0, 47, f'{freq:g} lp/mm（参考）', 10)
    period = scale / freq
    left, top, width, height = px(x0), px(58), px(42), px(25)
    k = 0
    while k * period < width:
        a = left + round(k * period)
        b = min(left + width, left + round((k + .5) * period))
        draw.rectangle((a, top, max(a, b - 1), top + height), fill=0)
        k += 1

# Slanted solid edge: useful visually; original camera pixels are still needed
# for any meaningful slanted-edge SFR measurement.
cx, cy, angle = 155, 135, radians(5)
points = []
for x, y in [(-22, -32), (22, -32), (22, 32), (-22, 32)]:
    points.append((px(cx + x * cos(angle) - y * sin(angle)),
                   px(cy + x * sin(angle) + y * cos(angle))))
draw.polygon(points, fill=0)
text(126, 171, '约 5° 倾斜黑白边缘', 10)

for i, points in enumerate([6, 8, 10, 12, 16]):
    text(16, 96 + i * 14, '清晰对焦 ABCDE 0123456789', points)
for y in range(100, 165, 4):
    draw.line((px(219), px(y), px(274), px(y)), fill=0, width=max(1, px(.15)))
text(217, 171, '观察细线与边缘重影', 10)
text(14, 187, '本卡用于对焦辅助，不是标定棋盘，也不是经过认证的 MTF/SFR 测试图卡。', 9)
out = root / 'targets/focus_target_A4.png'
image.save(out, dpi=(dpi, dpi))
print(out)
