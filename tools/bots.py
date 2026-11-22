#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟玩家：一个人也能把整局流程走一遍。

先在浏览器里创建房间（你当房主），然后：

    python3 tools/bots.py 1234          # 1234 换成房间号，自动补满剩下的座位
    python3 tools/bots.py 1234 5        # 只加 5 个机器人
    python3 tools/bots.py 1234 --base=https://你的网址

机器人会自己入座、看身份、夜里行动、上警、投票。房主的操作（发牌、推进流程等）
还是由你在浏览器里点。
"""
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = 'http://localhost:3210'
NAMES = ['阿狸', '豆包', '老陈', '小满', '七七', '大白', '南瓜', '木木', '可乐', '夏天',
         '橘子', '阿福', '团子', '小北', '麦子', '星星', '柚子']


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode('utf-8'),
                                 {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode('utf-8') or '{}')


class Bot(threading.Thread):
    def __init__(self, code, name, delay):
        threading.Thread.__init__(self)
        self.daemon = True
        self.name_ = name
        self.delay = delay
        self.cred = post('/api/join', {'code': code, 'name': name})
        if 'pid' not in self.cred:
            raise SystemExit('进不了房间：%s' % self.cred)
        self.done = set()               # 已经处理过的环节，避免重复操作

    def act(self, typ, **data):
        return post('/api/act', {'code': self.cred['code'], 'pid': self.cred['pid'],
                                 'token': self.cred['token'], 'type': typ, 'data': data})

    def run(self):
        url = '%s/api/events?code=%s&pid=%s&token=%s' % (
            BASE, self.cred['code'], self.cred['pid'], self.cred['token'])
        with urllib.request.urlopen(url) as r:
            for raw in r:
                line = raw.decode('utf-8').strip()
                if line.startswith('data: '):
                    try:
                        self.handle(json.loads(line[6:]))
                    except Exception as e:      # 机器人出错不要影响别人
                        print('[%s] 出错：%r' % (self.name_, e))

    def once(self, *key):
        """同一个环节只操作一次。"""
        key = json.dumps(key, sort_keys=True, ensure_ascii=False)
        if key in self.done:
            return False
        self.done.add(key)
        time.sleep(self.delay * random.uniform(0.6, 1.4))
        return True

    def handle(self, v):
        me = v['you']
        ph = v['phase']
        if ph == 'lobby':
            self.done.clear()
            if not me['seat']:
                free = [s['seat'] for s in v['seats'] if not s['taken']]
                if free:
                    time.sleep(random.uniform(0, 0.3))
                    self.act('sit', seat=random.choice(free))
        elif ph == 'deal':
            if v.get('me') and not v['deal']['seen'] and self.once('seen'):
                self.act('seen')
        elif ph == 'night':
            p = v['night']['prompt']
            if p:
                self.night(v, p)
        elif ph == 'day':
            self.day(v)

    def night(self, v, p):
        me = v['you']['seat']
        n = v['night_no']
        ui = p['ui']
        if ui in ('info', 'result'):
            if self.once(n, p['type'], ui):
                self.act('night', ok=True)
        elif ui == 'pick':
            if not self.once(n, p['type'], ui):
                return
            if len(p['targets']) < p['count'] or (p['skip'] and random.random() < 0.3):
                self.act('night', skip=True)
            else:
                self.act('night', targets=random.sample(p['targets'], p['count']))
        elif ui == 'witch':
            if not self.once(n, 'witch'):
                return
            x = random.random()
            if p['can_save'] and x < 0.6:
                self.act('witch', save=True)
            elif p['poison'] and x > 0.8:
                self.act('witch', poison=random.choice(p['targets']))
            else:
                self.act('witch')
        elif ui == 'wolf':
            picks = {int(k): x for k, x in p['picks'].items()}
            if p['agreed'] is not None:
                if me == min(p['wolves']) and self.once(n, 'wolf-confirm', p['agreed']):
                    self.act('wolf_confirm')
                return
            decided = [w for w in p['wolves'] if w in picks]       # 跟着已经选了的人
            if decided and picks.get(me) != picks[decided[0]]:
                if self.once(n, 'wolf-follow', picks[decided[0]]):
                    self.act('wolf_pick', target=picks[decided[0]])
            elif not decided and me == min(p['wolves']) and self.once(n, 'wolf-lead'):
                good = [s for s in p['targets'] if s not in p['wolves']]
                self.act('wolf_pick', target=random.choice(good or p['targets']))

    def day(self, v):
        d = v['day']
        no = d['no']
        mine = (d.get('settle') or {}).get('mine')
        if mine and self.once(no, 'settle', len(d['feed'])):
            data = {'target': random.choice(d['settle']['targets']) if mine['can_shoot'] else 0}
            if mine['badge']:
                data['badge'] = random.choice(d['settle']['targets'])
            self.act('settle', **data)
        vt = d.get('vote')
        if vt and vt['can'] and self.once(no, 'vote', vt['round']):
            self.act('vote', target=random.choice(vt['cands'] + [0]))
        e = d.get('elect')
        if e and e['mine'] == 'signup' and self.once(no, 'signup'):
            self.act('elect_run', run=random.random() < 0.3)
        if e and e['mine'] == 'withdraw' and self.once(no, 'withdraw'):
            self.act('elect_withdraw', out=random.random() < 0.25)
        if e and e['mine'] == 'vote' and self.once(no, 'evote', e['vote']['round']):
            self.act('elect_vote', target=random.choice(e['vote']['cands'] + [0]))
        if d.get('order') and d['order']['mine'] and self.once(no, 'order'):
            self.act('order', i=random.choice([0, 1]))


def main():
    global BASE
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for a in sys.argv[1:]:
        if a.startswith('--base='):
            BASE = a.split('=', 1)[1].rstrip('/')
    if not args:
        raise SystemExit(__doc__)
    code = args[0]
    delay = 1.2
    probe = Bot(code, NAMES[0], delay)
    probe.start()
    time.sleep(0.5)
    want = int(args[1]) if len(args) > 1 else None
    if want is None:
        # 看看还差几个座位
        req = urllib.request.urlopen('%s/api/events?code=%s&pid=%s&token=%s' % (
            BASE, code, probe.cred['pid'], probe.cred['token']))
        for raw in req:
            line = raw.decode('utf-8').strip()
            if line.startswith('data: '):
                v = json.loads(line[6:])
                want = sum(1 for s in v['seats'] if not s['taken']) + 1
                break
        req.close()
    bots = [probe]
    for i in range(1, want):
        b = Bot(code, NAMES[i % len(NAMES)], delay)
        b.start()
        bots.append(b)
        time.sleep(0.15)
    print('%d 个机器人已进入房间 %s，按 Ctrl+C 让它们离开' % (len(bots), code))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
