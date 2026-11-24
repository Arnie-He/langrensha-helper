#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载界面用的手写风字体子集（站酷小薇体，OFL 许可）。

只取界面里真正出现过的字：扫一遍源码里的所有汉字，交给 Google Fonts 现切一份子集，
存到 public/fonts/，再生成 public/fonts/fonts.css。玩家昵称里的生僻字会回退到系统字体。

    python3 tools/fonts/fetch.py

改了界面文案、出现了新的字以后重跑一次即可。
"""
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
OUT = os.path.join(ROOT, 'public', 'fonts')
FAMILY = 'ZCOOL XiaoWei'
SOURCES = ['public/app.js', 'public/fx.js', 'public/index.html', 'game.py', 'roles.py', 'clips.py', 'server.py']
EXTRA = '，。、：；？！（）「」《》“”‘’—…·×→←＋－／％〇零一二三四五六七八九十百千'
# 这款字体里画坏了的字（「回」的内外两圈画成了一个实心方块），不放进子集，让它们用系统宋体显示
BROKEN = '回'
CHUNK = 160                      # 每次请求的字数（网址太长会被拒绝）
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0 Safari/537.36')


def chars():
    seen = set(EXTRA)
    for f in SOURCES:
        with open(os.path.join(ROOT, f), encoding='utf-8') as fh:
            for c in fh.read():
                if '一' <= c <= '鿿' or c in '，。、：；？！（）「」《》“”‘’—…·×→':
                    seen.add(c)
    return sorted(seen - set(BROKEN))


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def ranges(cs):
    """把一组字符写成 unicode-range。"""
    cps = sorted(ord(c) for c in cs)
    out, a, b = [], cps[0], cps[0]
    for c in cps[1:]:
        if c == b + 1:
            b = c
            continue
        out.append((a, b))
        a = b = c
    out.append((a, b))
    return ','.join('U+%X' % a if a == b else 'U+%X-%X' % (a, b) for a, b in out)


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.woff2'):
            os.remove(os.path.join(OUT, f))
    han = chars()
    latin = [chr(i) for i in range(0x20, 0x7f)]
    groups = [latin] + [han[i:i + CHUNK] for i in range(0, len(han), CHUNK)]
    css, total = [], 0
    for i, g in enumerate(groups):
        url = 'https://fonts.googleapis.com/css2?family=%s&text=%s' % (
            FAMILY.replace(' ', '+'), urllib.parse.quote(''.join(g)))
        sheet = get(url).decode('utf-8')
        m = re.search(r'url\((https://[^)]+)\)\s*format\([\'"]woff2[\'"]\)', sheet)
        if not m:
            raise SystemExit('没拿到 woff2：\n' + sheet[:400])
        data = get(m.group(1))
        name = 'xiaowei-%d.woff2' % i
        with open(os.path.join(OUT, name), 'wb') as fh:
            fh.write(data)
        total += len(data)
        css.append("@font-face{font-family:'XiaoWei';font-style:normal;font-weight:400;font-display:swap;"
                   "src:url(%s) format('woff2');unicode-range:%s}" % (name, ranges(g)))
        print('%-18s %4d 字 %6.1f KB' % (name, len(g), len(data) / 1024.0))
    with open(os.path.join(OUT, 'fonts.css'), 'w', encoding='utf-8') as fh:
        fh.write('/* 站酷小薇体（ZCOOL XiaoWei，SIL OFL 1.1）的子集，由 tools/fonts/fetch.py 生成 */\n')
        fh.write('\n'.join(css) + '\n')
    print('共 %d 个汉字，%d 个文件，%.0f KB' % (len(han), len(groups), total / 1024.0))


if __name__ == '__main__':
    main()
