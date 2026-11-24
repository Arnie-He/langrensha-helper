#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 macOS 自带的语音合成，把 clips.py 里的台词生成音频文件。

    python3 tools/gen_audio.py              # 默认用「婷婷」的声音
    python3 tools/gen_audio.py Meijia 170   # 换声音、换语速
    python3 tools/gen_audio.py --only=elect_tie,elect_vote_pk   # 只重新生成这几条

只能在 Mac 上运行（用到 say 和 afconvert）。生成的文件在 public/audio/ 里，
也可以直接用自己录的 .m4a 替换同名文件。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from clips import CLIPS  # noqa: E402

OUT = os.path.join(ROOT, 'public', 'audio')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    only = [a.split('=', 1)[1].split(',') for a in sys.argv[1:] if a.startswith('--only=')]
    only = set(only[0]) if only else None
    voice = args[0] if len(args) > 0 else 'Tingting'
    rate = args[1] if len(args) > 1 else '165'
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    if only:
        with open(os.path.join(OUT, 'manifest.json'), encoding='utf-8') as f:
            manifest = json.load(f)
    with tempfile.TemporaryDirectory() as tmp:
        aiff = os.path.join(tmp, 'x.aiff')
        for cid, text in sorted(CLIPS.items()):
            if only and cid not in only:
                continue
            subprocess.check_call(['say', '-v', voice, '-r', rate, '-o', aiff, text])
            m4a = os.path.join(OUT, cid + '.m4a')
            subprocess.check_call(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '64000',
                                   aiff, m4a])
            info = subprocess.check_output(['afinfo', m4a]).decode('utf-8', 'replace')
            dur = float(re.search(r'estimated duration: ([\d.]+)', info).group(1))
            manifest[cid] = round(dur, 2)
            print('%-16s %5.2fs  %s' % (cid, dur, text))
    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=0, sort_keys=True)
    print('共 %d 条，%.0f 秒' % (len(manifest), sum(manifest.values())))


if __name__ == '__main__':
    main()
