#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把所有手绘素材画出来：角色头像写到 public/avatars/，界面素材写到 public/art/。

    python3 tools/sketch/build.py            # 全部重画
    python3 tools/sketch/build.py --sheet    # 另外生成 public/_sheet.html，方便一眼看完所有素材
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PUB = os.path.join(HERE, '..', '..', 'public')

import portraits  # noqa: E402

try:
    import ui_art  # noqa: E402
except ImportError:
    ui_art = None


def write(path, text):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return len(text.encode('utf-8'))


def main():
    total = 0
    os.makedirs(os.path.join(PUB, 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(PUB, 'art'), exist_ok=True)
    for name, fn in portraits.ROLES:
        total += write(os.path.join(PUB, 'avatars', name + '.svg'), portraits.render(name, fn))
    arts = []
    if ui_art:
        for name, svg in ui_art.build():
            arts.append(name)
            total += write(os.path.join(PUB, 'art', name + '.svg'), svg)
    print('%d 个头像，%d 个界面素材，共 %.0f KB' % (len(portraits.ROLES), len(arts), total / 1024.0))
    if '--sheet' in sys.argv:
        cells = ''.join('<figure><img src="avatars/%s.svg"><img class="s" src="avatars/%s.svg"><figcaption>%s</figcaption></figure>'
                        % (n, n, n) for n, _ in portraits.ROLES)
        cells += ''.join('<figure class="a"><img src="art/%s.svg"><figcaption>%s</figcaption></figure>' % (n, n) for n in arts)
        write(os.path.join(PUB, '_sheet.html'),
              '<!doctype html><meta charset="utf-8"><style>body{margin:8px;background:#2a231c;color:#d9caa5;font:11px sans-serif;'
              'display:flex;flex-wrap:wrap;gap:8px}figure{margin:0;text-align:center}img{display:block;width:150px;height:150px;'
              'border-radius:50%}img.s{width:36px;height:36px;margin:4px auto}.a img{border-radius:0;height:auto;max-height:240px;'
              'background:#8a7a5c}</style>' + cells)


if __name__ == '__main__':
    main()
