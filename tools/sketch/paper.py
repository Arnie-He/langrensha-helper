#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纸张底纹：一张可以无缝平铺的旧纸（paper.jpg）和一张深色的桌面（dark.jpg）。

需要 Pillow（只有重新生成底纹时才用到，运行游戏不需要）：
    python3 tools/sketch/paper.py
"""
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'public', 'art')
HALF = 160


def noise(size, sigma, blur, seed):
    random.seed(seed)
    im = Image.effect_noise((size, size), sigma)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def tile(base, grain, blotch, fibres, seed, fibre_col):
    """先画四分之一，再左右、上下镜像拼起来，这样四边一定接得上。"""
    r, g, b = base
    fine = noise(HALF, grain, 0, seed)
    big = noise(HALF // 8, blotch, 1, seed + 1).resize((HALF, HALF), Image.BICUBIC)
    lum = ImageChops.add(fine, big, scale=2, offset=0)
    q = Image.merge('RGB', [lum.point(lambda v, c=c: max(0, min(255, c + (v - 128)))) for c in (r, g, b)])
    d = ImageDraw.Draw(q)
    rnd = random.Random(seed + 2)
    for _ in range(fibres):
        x, y = rnd.uniform(0, HALF), rnd.uniform(0, HALF)
        dx, dy = rnd.uniform(-9, 9), rnd.uniform(-3, 3)
        d.line([(x, y), (x + dx, y + dy)], fill=fibre_col, width=1)
    q = q.filter(ImageFilter.GaussianBlur(.5))
    full = Image.new('RGB', (HALF * 2, HALF * 2))
    full.paste(q, (0, 0))
    full.paste(q.transpose(Image.FLIP_LEFT_RIGHT), (HALF, 0))
    full.paste(q.transpose(Image.FLIP_TOP_BOTTOM), (0, HALF))
    full.paste(q.transpose(Image.ROTATE_180), (HALF, HALF))
    return full


def main():
    os.makedirs(OUT, exist_ok=True)
    tile((217, 202, 165), 14, 22, 70, 11, (196, 180, 142)).save(os.path.join(OUT, 'paper.jpg'), quality=74, optimize=True)
    tile((36, 30, 24), 9, 14, 50, 23, (52, 44, 35)).save(os.path.join(OUT, 'dark.jpg'), quality=74, optimize=True)
    for f in ('paper.jpg', 'dark.jpg'):
        print('%-10s %d KB' % (f, os.path.getsize(os.path.join(OUT, f)) // 1024))


if __name__ == '__main__':
    main()
