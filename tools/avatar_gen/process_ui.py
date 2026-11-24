"""把 raw/ui_*.png 处理成网页用的小文件，放到 public/art/。

透明的（标题、月亮、太阳）裁掉透明边后存 WebP；背景和卡背存 JPEG。
    python3 tools/avatar_gen/process_ui.py
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'public', 'art')
os.makedirs(OUT, exist_ok=True)

ALPHA = {'logo': 760, 'moon': 256, 'sun': 256,       # 名字: 最长边
         'potion_save': 200, 'potion_poison': 200, 'emblem_good': 280, 'emblem_wolf': 280, 'badge_sheriff': 120}
OPAQUE = {'cardback': 640, 'bg_dusk': 1350, 'bg_night': 1350, 'bg_day': 1350}

for name, size in ALPHA.items():
    src = os.path.join(HERE, 'raw', 'ui_%s.png' % name)
    if not os.path.exists(src):
        continue
    im = Image.open(src).convert('RGBA')
    box = im.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    im = im.crop(box)
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(os.path.join(OUT, name + '.webp'), quality=88, method=6)

for name, size in OPAQUE.items():
    src = os.path.join(HERE, 'raw', 'ui_%s.png' % name)
    if not os.path.exists(src):
        continue
    im = Image.open(src).convert('RGB')
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(os.path.join(OUT, name + '.jpg'), quality=80, optimize=True, progressive=True)

for f in sorted(os.listdir(OUT)):
    p = os.path.join(OUT, f)
    w, h = Image.open(p).size
    print('%-14s %4dx%-4d %4d KB' % (f, w, h, os.path.getsize(p) // 1024))
