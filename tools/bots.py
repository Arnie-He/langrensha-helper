#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟玩家：一个人也能把整局流程走一遍。

先在浏览器里创建房间（你当房主），然后：

    python3 tools/bots.py 1234          # 1234 换成房间号，自动补满剩下的座位
    python3 tools/bots.py 1234 5        # 只加 5 个机器人
    python3 tools/bots.py 1234 --base=https://你的网址
    python3 tools/bots.py 1234 --flaky=20   # 机器人平均每 20 秒掉一次线，过一会儿再连回来

机器人会自己入座、看身份、夜里行动、上警、投票。房主的操作（发牌、推进流程等）
还是由你在浏览器里点。想要连房主也自动（整局无人值守，用来做压力测试），见 tools/soak.py。
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
# 掉线以后离开多久（秒）。服务器的宽限期是 6 秒：短的不会显示掉线，长的会。
AWAY = [0.2, 0.5, 1, 2, 3, 5, 8, 12, 20]


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode('utf-8'),
                                 {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode('utf-8') or '{}')
        except ValueError:
            return {'error': 'HTTP %d' % e.code}
    except (OSError, ValueError) as e:
        return {'error': repr(e)}


class Bot(threading.Thread):
    """一个模拟玩家。

    host=True   同时扮演房主：「播放」语音（按片段数等一小会儿再回报播完）、点各种推进流程的按钮
    flaky=秒    平均每隔这么久掉一次线：有时是连接断开过一会儿再连，有时是页面被冻住（连接还在但不回应心跳）
    """

    def __init__(self, code, name, delay, cred=None, host=False, flaky=0, clip=0.15):
        threading.Thread.__init__(self)
        self.daemon = True
        self.name_ = name
        self.delay = delay
        self.host = host
        self.flaky = flaky
        self.clip = clip
        self.cred = cred or post('/api/join', {'code': code, 'name': name})
        if 'pid' not in self.cred:
            raise SystemExit('进不了房间：%s' % self.cred)
        self.done = set()               # 已经处理过的环节，避免重复操作
        self.wait = {}                  # 操作失败以后，这个环节过多久才再试
        self.fresh = threading.Event()  # 来了新画面
        self.acked = 0                  # 房主：播到第几条语音了
        self.last = None                # 最近一次收到的画面
        self.sig = None                 # 游戏进度的摘要，用来发现「卡住了」
        self.moved = time.time()        # 进度最后一次变化的时间
        self.drops = 0                  # 掉过几次线
        self.errors = []
        self.quit = False

    def act(self, typ, **data):
        return post('/api/act', {'code': self.cred['code'], 'pid': self.cred['pid'],
                                 'token': self.cred['token'], 'type': typ, 'data': data})

    def beat(self):
        post('/api/beat', {'code': self.cred['code'], 'pid': self.cred['pid'],
                           'token': self.cred['token']})

    # ------------------------------------------------------------ 连接

    def run(self):
        for fn in [self.work] + ([self.tick] if self.host else []):
            t = threading.Thread(target=fn)
            t.daemon = True
            t.start()
        url = '%s/api/events?hb=1&code=%s&pid=%s&token=%s' % (
            BASE, self.cred['code'], self.cred['pid'], self.cred['token'])
        while not self.quit:
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    until = None
                    ev = ''
                    for raw in r:
                        line = raw.decode('utf-8').rstrip('\n')
                        if line.startswith('event: '):
                            ev = line[7:]
                        elif line.startswith('data: '):
                            if ev == 'ping':
                                self.beat()
                            else:
                                self.on_view(json.loads(line[6:]))
                            ev = ''
                        # 只在游戏进行中掉线：大厅里要全员在线才能发牌，那时大家本来也都盯着手机
                        if self.flaky and until is None and self.last and self.last['phase'] in ('night', 'day'):
                            until = time.time() + random.expovariate(1.0 / self.flaky)
                        if self.quit or (until and time.time() > until):
                            break
                    if until and not self.quit and random.random() < 0.3:
                        time.sleep(random.uniform(18, 24))      # 页面被冻住：连接没断，但不读也不回应心跳
            except Exception:           # 连接断了、服务器重启了：等一下再连
                pass
            if self.quit:
                break
            self.drops += 1
            time.sleep(random.choice(AWAY) if self.flaky else 1.0)

    def on_view(self, v):
        """收到新画面：只记下来。真正的操作在 work 里做，那边永远只看最新的一份（和真手机一样）。"""
        if v['phase'] in ('lobby', 'deal') and (self.last or {}).get('phase') not in ('lobby', 'deal'):
            self.done.clear()           # 新的一局：上一局做过的事不算数了
            self.wait.clear()
        self.last = v
        sig = self.progress(v)
        if sig != self.sig:
            self.sig = sig
            self.moved = time.time()
        self.fresh.set()

    def work(self):
        while not self.quit:
            self.fresh.wait(1.0)
            self.fresh.clear()
            v = self.last
            if not v:
                continue
            try:
                self.handle(v)
            except Exception as e:      # 机器人出错不要影响别人，但要记下来
                self.errors.append(repr(e))
                print('[%s] 出错：%r' % (self.name_, e))

    @staticmethod
    def progress(v):
        """只看游戏本身走到哪了，不看谁在线谁掉线。"""
        d = v.get('day') or {}
        e = d.get('elect') or {}
        vote = d.get('vote') or (e.get('vote') or {})
        return json.dumps([v['phase'], v.get('night_no'), bool((v.get('night') or {}).get('prompt')),
                           d.get('stage'), len(d.get('feed') or []), len(e.get('decided') or []),
                           len(vote.get('voted') or []), len((d.get('settle') or {}).get('waiting') or []),
                           [c['id'] for c in v.get('cues') or []],
                           sum(1 for s in v['seats'] if s['taken']), len((v.get('deal') or {}).get('ready') or [])])

    def do(self, key, typ, **data):
        """同一个环节只成功操作一次；失败了（比如画面已经过时）下次收到新画面再试。"""
        key = json.dumps(key, sort_keys=True, ensure_ascii=False)
        if key in self.done or self.wait.get(key, 0) > time.time():
            return False
        self.done.add(key)
        time.sleep(self.delay * random.uniform(0.6, 1.4))
        r = self.act(typ, **data)
        if not r.get('ok'):
            self.done.discard(key)
            self.wait[key] = time.time() + 1.5
            return False
        return True

    # ------------------------------------------------------------ 玩家的操作

    def handle(self, v):
        me = v['you']
        ph = v['phase']
        if self.host:
            self.speak(v)
        if ph == 'lobby':
            if not me['seat']:
                free = [s['seat'] for s in v['seats'] if not s['taken']]
                if free:
                    time.sleep(random.uniform(0, 0.3))
                    self.act('sit', seat=random.choice(free))
        elif ph == 'deal':
            if v.get('me') and not v['deal']['seen']:
                self.do(['seen'], 'seen')
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
            self.do([n, p['type'], ui], 'night', ok=True)
        elif ui == 'pick':
            if len(p['targets']) < p['count'] or (p['skip'] and random.random() < 0.3):
                self.do([n, p['type'], ui], 'night', skip=True)
            else:
                self.do([n, p['type'], ui], 'night', targets=random.sample(p['targets'], p['count']))
        elif ui == 'witch':
            x = random.random()
            if p['can_save'] and x < 0.6:
                self.do([n, 'witch'], 'witch', save=True)
            elif p['poison'] and x > 0.8:
                self.do([n, 'witch'], 'witch', poison=random.choice(p['targets']))
            else:
                self.do([n, 'witch'], 'witch')
        elif ui == 'wolf':
            picks = {int(k): x for k, x in p['picks'].items()}
            if p['agreed'] is not None:
                if me == min(p['wolves']):
                    self.do([n, 'wolf-confirm', p['agreed']], 'wolf_confirm')
                return
            decided = [w for w in p['wolves'] if w in picks]       # 跟着已经选了的人
            if decided and picks.get(me) != picks[decided[0]]:
                self.do([n, 'wolf-follow', picks[decided[0]]], 'wolf_pick', target=picks[decided[0]])
            elif not decided and me == min(p['wolves']):
                good = [s for s in p['targets'] if s not in p['wolves']]
                self.do([n, 'wolf-lead'], 'wolf_pick', target=random.choice(good or p['targets']))

    def day(self, v):
        d = v['day']
        no = d['no']
        mine = (d.get('settle') or {}).get('mine')
        if mine:
            data = {'target': random.choice(d['settle']['targets']) if mine['can_shoot'] else 0}
            if mine['badge']:
                data['badge'] = random.choice(d['settle']['targets'])
            self.do([no, 'settle', len(d['feed'])], 'settle', **data)
        vt = d.get('vote')
        if vt and vt['can']:
            self.do([no, 'vote', vt['round']], 'vote', target=random.choice(vt['cands'] + [0]))
        e = d.get('elect')
        if e and e['mine'] == 'signup':
            self.do([no, 'signup'], 'elect_run', run=random.random() < 0.3)
        if e and e['mine'] == 'withdraw':
            self.do([no, 'withdraw'], 'elect_withdraw', out=random.random() < 0.25)
        if e and e['mine'] == 'vote':
            self.do([no, 'evote', e['vote']['round']], 'elect_vote', target=random.choice(e['vote']['cands'] + [0]))
        if d.get('order') and d['order']['mine']:
            self.do([no, 'order'], 'order', i=random.choice([0, 1]))

    # ------------------------------------------------------------ 房主的操作

    def speak(self, v):
        """假装播语音：每个片段等一小会儿，然后回报播完了。"""
        for c in v.get('cues') or []:
            if c['id'] > self.acked:
                time.sleep(self.clip * len(c['clips']))
                self.act('ack', id=c['id'])
                self.acked = c['id']
                return

    def tick(self):
        """房主每半秒看一眼现在该点什么。"""
        while not self.quit:
            time.sleep(0.5)
            v = self.last
            if not v or not v['you'].get('host'):
                continue
            try:
                self.duty(v)
            except Exception as e:
                self.errors.append(repr(e))
                print('[房主] 出错：%r' % e)

    def duty(self, v):
        ph = v['phase']
        if any(c['id'] <= self.acked for c in v.get('cues') or []):
            self.act('ack', id=self.acked)                         # 回报丢了就补发
        if ph == 'lobby':
            if not v.get('err') and all(s['taken'] and s['online'] for s in v['seats']):
                self.act('deal')
        elif ph == 'deal':
            if v['deal']['count'] >= len(v['seats']):
                self.do(['night', 0], 'start_night')
        elif ph == 'day':
            d = v['day']
            st, no, e = d['stage'], d['no'], d.get('elect') or {}
            if st in ('e_speech', 'e_pk'):
                self.do([no, st, len(d['feed'])], 'elect_next')
            elif st in ('discuss', 'pk'):
                self.do([no, st, len(d['feed'])], 'start_vote')
            elif st == 'dusk':
                self.do([no, 'dusk'], 'start_night')
            elif time.time() - self.moved > 25:
                # 有人迟迟不操作（多半是掉线了）：房主点「不等了 / 结束投票」
                if st in ('e_signup', 'e_withdraw', 'e_vote'):
                    self.act('elect_close')
                elif st == 'vote':
                    self.act('end_vote')
                elif st == 'settle' and not (d.get('settle') or {}).get('mine'):
                    self.act('settle_close')
        elif ph == 'night' and time.time() - self.moved > 45:
            self.act('skip')                                       # 轮到的人一直没回来：跳过这个环节


def main():
    global BASE
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flaky = 0
    for a in sys.argv[1:]:
        if a.startswith('--base='):
            BASE = a.split('=', 1)[1].rstrip('/')
        if a.startswith('--flaky='):
            flaky = float(a.split('=', 1)[1])
    if not args:
        raise SystemExit(__doc__)
    code = args[0]
    delay = 1.2
    probe = Bot(code, NAMES[0], delay, flaky=flaky)
    probe.start()
    time.sleep(0.5)
    want = int(args[1]) if len(args) > 1 else None
    if want is None:
        # 看看还差几个座位（第一个机器人可能已经坐下了，也可能还没有）
        for _ in range(100):
            if probe.last:
                break
            time.sleep(0.05)
        v = probe.last or {'seats': [], 'you': {'seat': 0}}
        want = sum(1 for s in v['seats'] if not s['taken']) + (1 if v['you']['seat'] else 0)
    bots = [probe]
    for i in range(1, want):
        b = Bot(code, NAMES[i % len(NAMES)], delay, flaky=flaky)
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
