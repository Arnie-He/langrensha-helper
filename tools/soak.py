#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""压力测试：全是机器人（连房主也是），在不停掉线的情况下把整局打完，连打几局。

先启动服务器（LRS_FAST=1 会把夜里的停顿缩短，跑得快一些）：

    LRS_DEV=1 LRS_FAST=1 PORT=3299 python3 server.py

然后：

    python3 tools/soak.py --base=http://localhost:3299 --games=3 --flaky=12
    python3 tools/soak.py --base=... --board=p12g --flaky=8 --flaky-host

    --board=     板子：预设的编号（p12a ...），或者 15（15 人 通灵师女巫猎人守卫骑士 + 狼王机械狼，默认）
    --flaky=     每个玩家平均多少秒掉一次线（0 = 不掉线）
    --flaky-host 房主的手机也会掉线
    --takeover   房主掉线或播报停了的时候，其他人会接手播报
    --poll=      有几个人不用长连接、只靠定时取画面（模拟长连接不通的网络）
    --relogin=   每次掉线后「手机丢了、重新进来认领座位」的概率（比如 0.1）
    --games=     连打几局

任何一局超过 --stall 秒（默认 120）没有任何进展，就打印当时的状态并以失败退出。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import bots  # noqa: E402
from roles import PRESETS  # noqa: E402

BOARD15 = {'wolf': 3, 'wolfking': 1, 'mech': 1, 'psychic': 1, 'witch': 1, 'hunter': 1,
           'guard': 1, 'knight': 1, 'villager': 5}


def opt(name, default):
    for a in sys.argv[1:]:
        if a.startswith('--%s=' % name):
            return a.split('=', 1)[1]
    return default


def main():
    bots.BASE = opt('base', 'http://localhost:3299').rstrip('/')
    games = int(opt('games', '2'))
    flaky = float(opt('flaky', '12'))
    stall = float(opt('stall', '120'))
    board = opt('board', '15')
    roles = BOARD15 if board == '15' else next(p['roles'] for p in PRESETS if p['id'] == board)
    n = sum(roles.values())

    takeover = '--takeover' in sys.argv
    polls = int(opt('poll', '0'))
    relogin = float(opt('relogin', '0'))

    cred = bots.post('/api/create', {'name': '房主', 'roles': roles})
    if 'pid' not in cred:
        raise SystemExit('建不了房间：%s' % cred)
    host = bots.Bot(cred['code'], '房主', 0.3, cred=cred, host=True, takeover=takeover,
                    flaky=flaky if '--flaky-host' in sys.argv else 0)
    host.start()
    crew = [host]
    for i in range(1, n):
        b = bots.Bot(cred['code'], bots.NAMES[i % len(bots.NAMES)] + str(i), 0.3, flaky=flaky,
                     takeover=takeover, poll=i <= polls, relogin=relogin)
        b.start()
        crew.append(b)
        time.sleep(0.05)
    print('房间 %s：%d 人，%s，掉线间隔 %s 秒%s%s%s' % (
        cred['code'], n, board, flaky or '不掉线', '，会换人播报' if takeover else '',
        '，%d 人只轮询' % polls if polls else '', '，丢手机概率 %s' % relogin if relogin else ''))

    played, t0, last_phase = 0, time.time(), None
    while played < games:
        time.sleep(0.5)
        fresh = max(crew, key=lambda b: b.viewed)        # 画面最新的那台手机
        v = fresh.last
        if not v:
            continue
        now = '%s %s' % (v['phase'], v.get('night_no') or '')
        if now != last_phase:
            last_phase = now
            print('  %5.0f 秒  %s  掉线中：%s' % (time.time() - t0, now, [s['seat'] for s in v['seats'] if not s['online']]))
        if v['phase'] == 'over':
            played += 1
            o = v['over']
            print('第 %d 局结束：%s 获胜，%d 夜，用时 %.0f 秒，累计掉线 %d 次，换人播报 %d 次，重新认领座位 %d 次'
                  % (played, o['winner'], v['night_no'], time.time() - t0, sum(b.drops for b in crew),
                     sum(b.takeovers for b in crew), sum(b.claims for b in crew)))
            t0 = time.time()
            if played < games:
                time.sleep(1)
                for _ in range(40):                       # 现在谁是房主谁来开下一局（房主可能刚好掉线，等一等）
                    if any(b.act('again').get('ok') for b in crew):
                        break
                    time.sleep(1)
                for b in crew:
                    b.moved = time.time()
                time.sleep(1)
            continue
        quiet = min(time.time() - b.moved for b in crew)
        if time.time() - t0 > 900:
            quiet, stall = time.time() - t0, 0            # 一局打了一刻钟还没完，也算卡住
        if quiet > stall:
            print('\n卡住了：%.0f 秒没有进展' % quiet)
            try:                                          # 开发模式的服务器可以直接问它房间的真实状态
                with bots.urllib.request.urlopen('%s/api/debug?act=state&code=%s' % (bots.BASE, cred['code']), timeout=5) as r:
                    print('服务器状态：', r.read().decode('utf-8'))
            except Exception as e:
                print('（问不到服务器状态：%r）' % e)
            print(json.dumps({k: v.get(k) for k in ('phase', 'night_no', 'night', 'day', 'cues', 'host_online', 'stalled')},
                             ensure_ascii=False)[:1500])
            print('掉线的座位：', [s['seat'] for s in v['seats'] if not s['online']])
            raise SystemExit(1)
    errs = [e for b in crew for e in b.errors]
    if errs:
        print('机器人出过错：', errs[:5])
        raise SystemExit(1)
    print('全部打完，没有卡住。')


if __name__ == '__main__':
    main()
