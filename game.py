# -*- coding: utf-8 -*-
"""狼人杀面杀助手 —— 游戏引擎（纯逻辑，不含网络）。

核心设计：语音和操作严格同步
--------------------------------
房主的手机负责外放语音。引擎把要播的话放进一个队列（cue），房主手机每播完
一条就回报一次（ack）。夜晚的每个角色环节都卡在这些回报上：

    「X请睁眼」播完  ->  X 的手机才出现操作界面，同时开始播操作提示
    X 在手机上操作完  ->  才播「X请闭眼」
    「X请闭眼」播完  ->  停顿两秒  ->  下一个角色

所以不会出现语音说到女巫、手机上却还停在狼人的情况。
如果某个角色已经出局，引擎会用一段随机时长假装他在操作，
其他人无法从节奏上听出这个角色是否还活着。
"""
import random
import secrets
import threading
import time

from clips import cue_text
from roles import (GODS, MAX_SEATS, MULTI, PRESETS, ROLES, ROLE_ORDER, default_config,  # noqa: F401
                   full_roles, night_steps, step_name, total_of, validate_config)


class GameError(Exception):
    """可以直接显示给玩家看的错误。"""


# 各段停顿（秒）。测试里会用假时钟，不会真的等。
PAUSE_AFTER_NIGHT_FALL = 3.0
PAUSE_BETWEEN_ROLES = 2.0
FAKE_ACT = {'witch': (11.0, 17.0), 'wolf': (8.0, 14.0), 'cupid': (8.0, 13.0),
            'magician': (7.0, 12.0)}
FAKE_DEFAULT = (6.0, 11.0)

# 掉线判定（秒）。手机锁屏、切到别的 App、换网络时连接会断一下再连上，不能一断就当成掉线。
OFFLINE_GRACE = 6.0          # 连接断开后，这么久还没连回来才算掉线
ALIVE_FOR = 16.0             # 连接还在，但这么久没有回应心跳（页面被系统冻结了），也算掉线
CUE_STALL = 25.0             # 一条语音排到队首这么久还没播完，就认为房主手机的播报卡住了
GHOST_AFTER = 60.0           # 进了房间却一直没连上来、也没入座的人，在大厅名单里留这么久就清掉
CLAIM_TTL = 300.0            # 「换手机回到座位」的申请，房主这么久没处理就作废
CLAIM_HOLD = 1800.0          # 批准以后，申请人的手机这么久之内拿起来都能直接进去（中途锁了屏也不怕）
CLAIM_KEEP = 64              # 最多记着多少条申请（含处理完的）。有人不停地申请又撤回时，先扔掉最早处理完的

# 只有这些死法可以发动猎人 / 狼王的枪
GUN_OK = ('wolf', 'vote', 'shot', 'take', 'hunt')
CAUSE_TEXT = {
    'wolf': '被刀', 'poison': '被毒', 'vote': '被放逐', 'shot': '被枪带走', 'boom': '自爆',
    'take': '被白狼王带走', 'love': '殉情', 'charm': '随狼美人殉情', 'dream': '梦游而死',
    'duel': '被骑士决斗', 'duel_fail': '决斗失败', 'reflect': '被恶灵骑士反伤',
    'hunt': '被猎魔人狩猎', 'backfire': '狩猎失败', 'bm': '血月使徒出局',
}
MECH_GAIN = {
    'psychic': '从明晚起，你每晚可以查验一名玩家的具体身份。',
    'gargoyle': '从明晚起，你每晚可以查验一名玩家的具体身份。',
    'seer': '从明晚起，你每晚可以查验一名玩家是好人还是狼人。',
    'witch': '你获得一瓶毒药，从明晚起可以使用。',
    'guard': '从明晚起，你每晚可以守护一名玩家。',
    'hunter': '你出局时可以开枪带走一名玩家。',
}
MECH_DOUBLE = '你获得一次双刀：带刀以后，可以一晚刀两个人，或者两刀砍同一人（无视解药和守护）。'


def clean_name(name):
    name = ''.join(ch for ch in str(name or '') if ch.isprintable()).strip()
    return name[:8] or '玩家'


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _join(seats):
    return '、'.join('%d号' % s for s in seats)


def _votes(x):
    return ('%g' % x) + '票'


def _default_later(sec, fn):
    t = threading.Timer(sec, fn)
    t.daemon = True
    t.start()


class Room(object):
    def __init__(self, code, later=None, rng=None, on_change=None, on_revoke=None):
        self.code = code
        self.lock = threading.RLock()
        self._later = later or _default_later
        self.rng = rng or random.SystemRandom()
        self.on_change = on_change or (lambda room: None)
        # 某人的身份作废了（座位被新手机认领走）：服务器据此掐断他旧手机上还开着的连接
        self.on_revoke = on_revoke or (lambda room, pid: None)
        self.claims = {}              # 换手机回到座位的申请 {编号: {...}}，要房主同意
        self.sits = 0                 # 坐下的次数，给每次入座一个编号
        self.players = {}
        self.host = None
        # 发牌时的房主。换手机回到座位的申请由他批准：中途接手播报的人只能批准他本人回来，
        # 免得有人先接手播报、再用另一台手机认领别人的座位、自己批准自己，看到别人的身份
        self.owner = None
        self.phase = 'lobby'          # lobby -> deal -> night <-> day -> over
        self.config = default_config()
        self.g = None                 # 一局游戏的全部状态
        self.cues = []                # 等待房主手机播报的语音队列
        self.cue_seq = 0
        self.cue_since = 0.0          # 队首那条语音是什么时候开始等的
        self.stalled = False          # 播报卡住了（见 sweep），这时别人可以接手播报
        self.epoch = 0                # 每次回到大厅 +1，让旧的定时器失效
        self.touched = time.time()
        self.created = self.touched

    # ================================================================== 基础设施

    def changed(self):
        self.on_change(self)

    def later(self, sec, fn):
        epoch = self.epoch

        def run():
            with self.lock:
                if self.epoch != epoch:
                    return
                fn()
                self.changed()
        self._later(sec, run)

    def cue(self, clips, gate=None):
        """排一条语音。gate 是这条语音播完以后才执行的动作。"""
        self.cue_seq += 1
        if not self.cues:
            self.cue_since = time.time()
            self.stalled = False                       # 新的一句刚排上来，谈不上卡住
        self.cues.append({'id': self.cue_seq, 'clips': list(clips), 'gate': gate})

    def when_quiet(self, fn):
        """等目前排着的语音全部播完再执行 fn。"""
        if not self.cues:
            fn()
            return
        last = self.cues[-1]
        prev = last['gate']

        def both():
            if prev:
                prev()
            fn()
        last['gate'] = both

    def ack(self, pid, cue_id):
        """房主手机回报：编号 <= cue_id 的语音已经播完。"""
        with self.lock:
            if pid != self.host:
                return
            while self.cues and self.cues[0]['id'] <= cue_id:
                c = self.cues.pop(0)
                self.cue_since = time.time()
                self.stalled = False
                if c['gate']:
                    c['gate']()
            self.changed()

    # ================================================================== 玩家进出

    @property
    def n(self):
        return total_of(self.config['roles'])

    def seat_map(self):
        return {p['seat']: p for p in self.players.values() if p['seat']}

    def add_player(self, name):
        # online 是别人看到的「在线 / 掉线」；conns 是这台手机现在有几条实时连接，其中 hbc 条会回应心跳；
        # seen 是最后一次有动静（连上来、回应心跳、轮询）的时间
        p = {'id': secrets.token_hex(4), 'token': secrets.token_hex(12),
             'name': clean_name(name), 'seat': 0, 'born': time.time(),
             'online': False, 'conns': 0, 'hbc': 0, 'seen': 0.0, 'left': 0.0}
        self.players[p['id']] = p
        if self.host is None:
            self.host = self.owner = p['id']
        return p

    def auth(self, pid, token):
        p = self.players.get(pid)
        if p and token and secrets.compare_digest(str(p['token']), str(token)):
            return p
        return None

    def attach(self, pid, hb=False, now=None):
        """这台手机连上来了一条实时连接。hb=True 表示它会定时回应心跳（见 touch）。"""
        with self.lock:
            p = self.players.get(pid)
            if p:
                p['conns'] += 1
                if hb:
                    p['hbc'] += 1
                p['seen'] = time.time() if now is None else now
                p['online'] = True
                self.touched = time.time()
                self.changed()

    def detach(self, pid, hb=False, now=None):
        """一条实时连接断了（hb 要和它连上来时说的一样）。先不算掉线：多半几秒内就会连回来，真没回来由 sweep 标记。"""
        with self.lock:
            p = self.players.get(pid)
            if not p:
                return
            p['conns'] = max(0, p['conns'] - 1)
            if hb:
                p['hbc'] = max(0, p['hbc'] - 1)
            if not p['conns']:
                p['hbc'] = 0
                p['left'] = time.time() if now is None else now

    def touch(self, pid, now=None):
        """这台手机刚刚有动静（回应了心跳，或者来取了一次画面）。"""
        with self.lock:
            p = self.players.get(pid)
            if not p:
                return False
            p['seen'] = time.time() if now is None else now
            if not p['online']:
                p['online'] = True
                self.changed()
            return True

    def sweep(self, now=None):
        """定时检查（服务器每两秒调一次）：标记真正掉线的人，发现播报卡住。

        掉线 = 连接断开超过 OFFLINE_GRACE 还没回来，或者连接还在但超过 ALIVE_FOR 没有回应心跳
        （手机锁屏后页面被系统冻结，连接表面上还在，其实收不到任何东西）。
        """
        now = time.time() if now is None else now
        with self.lock:
            dirty = False
            for pid, p in list(self.players.items()):
                if not p['online']:
                    # 页面没开成的人（进了房间但从来没连上来）：不清的话大厅名单只增不减
                    if (self.phase == 'lobby' and not p['seat'] and not p['conns'] and pid != self.host
                            and now - max(p['seen'], p['left'], p['born']) > GHOST_AFTER):
                        del self.players[pid]
                        dirty = True
                    continue
                if p['conns']:
                    # 只有当这个人所有的连接都会回应心跳时，才能凭「没回应」判断页面被冻住了；
                    # 只要有一条是不回应心跳的老页面 / 脚本，就只能看连接本身
                    gone = p['hbc'] >= p['conns'] and now - p['seen'] > ALIVE_FOR
                else:
                    gone = now - max(p['seen'], p['left']) > OFFLINE_GRACE
                if not gone:
                    continue
                p['online'] = False
                dirty = True
                # 大厅里没入座又掉线的人直接清掉，免得名单越来越长
                if self.phase == 'lobby' and not p['seat'] and pid != self.host:
                    del self.players[pid]
            if self._expire_claims(now):               # 没人处理的申请过期了：房主那边的横幅收起来
                dirty = True
            # 一句话里报的号码越多（比如报一长串上警的人），允许的时间越长
            stalled = bool(self.cues) and now - self.cue_since > CUE_STALL + 1.5 * len(self.cues[0]['clips'])
            if stalled != self.stalled:
                self.stalled = stalled
                dirty = True
            if dirty:
                self.changed()

    def offline_seats(self):
        """游戏进行中可以被重新认领的座位（原主人掉线了）。"""
        return [{'seat': p['seat'], 'name': p['name']}
                for p in sorted(self.players.values(), key=lambda x: x['seat'])
                if p['seat'] and not p['online']]

    # 换了手机或浏览器的人，用房间号重新进来认领自己原来的座位。
    # 认领必须经房主同意：否则只要知道房间号，谁都能趁别人锁屏的时候顶掉他的座位、看到他的身份。

    def _expire_claims(self, now):
        """清掉过期的申请；记录太多时再扔掉最早处理完的。返回房主那边的横幅是否因此少了。"""
        gone = [r for r, c in self.claims.items() if now - c['at'] > (CLAIM_HOLD if c['state'] == 'ok' else CLAIM_TTL)]
        live = any(self.claims[r]['state'] == 'wait' for r in gone)
        for rid in gone:
            del self.claims[rid]
        extra = len(self.claims) - CLAIM_KEEP
        if extra > 0:
            done = sorted((c for c in self.claims.values() if c['state'] == 'no'), key=lambda c: c['at'])
            for c in done[:extra]:
                del self.claims[c['rid']]
        return live

    def _may_approve(self, p, c):
        """p 能不能处理这个申请：发牌时的房主可以；接手播报的人只能处理原来房主本人的申请，
        除非原来的房主没有座位（换不了手机回来），那就由现在播报的人处理。"""
        if p['id'] == self.owner:
            return True
        if p['id'] != self.host:
            return False
        owner = self.players.get(self.owner)
        return not owner or not owner['seat'] or c['pid'] == owner['id']

    def _claim_live(self, c):
        """这个申请还有效吗：还在等房主，而且座位的主人仍然不在线。"""
        q = self.players.get(c['pid'])
        if c['state'] == 'wait' and (not q or q['seat'] != c['seat'] or q['online']):
            c['state'] = 'no'                          # 原来的手机回来了 / 座位变了：作废
        return c['state'] == 'wait'

    def request_claim(self, seat, name, now=None):
        """申请认领一个掉线的座位，返回申请编号。"""
        with self.lock:
            now = time.time() if now is None else now
            if self.phase == 'lobby':
                raise GameError('还没发牌，直接选座位就行')
            p = self.seat_map().get(_int(seat))
            if not p:
                raise GameError('没有这个座位')
            if p['online']:
                raise GameError('这个座位的玩家还在线')
            self._expire_claims(now)
            # 同一个座位只留最新的一个申请：房主那边每个座位最多一条横幅，
            # 一个座位上的重复申请也挤不掉别的座位的申请
            for c in self.claims.values():
                if c['seat'] == p['seat'] and c['state'] == 'wait':
                    c['state'] = 'no'
            rid = secrets.token_hex(8)
            self.claims[rid] = {'rid': rid, 'seat': p['seat'], 'pid': p['id'], 'at': now, 'state': 'wait',
                                'token': None, 'name': clean_name(name) if name and str(name).strip() else ''}
            self.changed()
            return rid

    def claim_status(self, rid, now=None):
        """申请的结果：('wait' | 'ok' | 'no' | 'gone', 同意后是那个座位的玩家)。"""
        with self.lock:
            self._expire_claims(time.time() if now is None else now)
            c = self.claims.get(str(rid or ''))
            if not c:
                return 'gone', None
            if c['state'] == 'ok':
                # 只交出这次批准时发的那个身份：之后座位又被别人认领过，这个编号就不再管用
                q = self.players.get(c['pid'])
                if q and q['token'] == c['token']:
                    return 'ok', q
                return 'gone', None
            self._claim_live(c)
            return c['state'], None

    def cancel_claim(self, rid):
        """申请人自己取消了申请。已经批准了的取消不了，返回和 claim_status 一样的结果。"""
        with self.lock:
            c = self.claims.get(str(rid or ''))
            if c and c['state'] == 'wait':
                c['state'] = 'no'
                self.changed()
        return self.claim_status(rid)

    def _claim_for(self, p, data):
        if p['id'] not in (self.host, self.owner):
            raise GameError('只有房主可以这样做')
        self._expire_claims(time.time())               # 横幅挂太久、申请人多半早走了的，不再生效
        c = self.claims.get(str(data.get('rid') or ''))
        if not c or not self._claim_live(c):
            raise GameError('这个申请已经失效了')
        if not self._may_approve(p, c):
            raise GameError('要等房主（%d 号）用手机回来才能处理' % self.players[self.owner]['seat'])
        return c

    def a_claim_ok(self, p, data):
        c = self._claim_for(p, data)
        q = self.players[c['pid']]
        q['token'] = secrets.token_hex(12)             # 旧手机上的身份从此作废
        if c['name']:
            q['name'] = c['name']
        c['state'] = 'ok'
        c['token'] = q['token']
        c['at'] = time.time()                          # 从批准时重新计时（CLAIM_HOLD），给申请人留足时间来取
        for o in self.claims.values():                 # 同一个座位的其他申请一并作废
            if o is not c and o['seat'] == c['seat'] and o['state'] == 'wait':
                o['state'] = 'no'
        self.on_revoke(self, q['id'])

    def a_claim_no(self, p, data):
        self._claim_for(p, data)['state'] = 'no'

    # ================================================================== 操作入口

    def action(self, pid, typ, data):
        with self.lock:
            p = self.players.get(pid)
            if not p:
                raise GameError('你不在这个房间里')
            fn = getattr(self, 'a_' + str(typ), None)
            if fn is None:
                raise GameError('未知操作')
            fn(p, data if isinstance(data, dict) else {})
            self.touched = time.time()
            self.changed()

    def _need_host(self, p):
        if p['id'] != self.host:
            raise GameError('只有房主可以这样做')

    def _alive(self):
        seats = self.g['seats']
        return [s for s in sorted(seats) if seats[s]['alive']]

    def _role(self, seat):
        return self.g['seats'][seat]['role']

    def _team(self, seat):
        return ROLES[self._role(seat)]['team']

    def _need_alive_target(self, target):
        st = self.g['seats'].get(target)
        if not st or not st['alive']:
            raise GameError('只能选择存活的玩家')
        return st

    def _note(self, seat, text):
        self.g['notes'][seat].append(text)

    def a_ack(self, p, data):
        self.ack(p['id'], _int(data.get('id')))

    # ================================================================== 大厅

    def a_sit(self, p, data):
        if self.phase != 'lobby':
            raise GameError('游戏已经开始，不能换座位')
        seat = _int(data.get('seat'))
        if seat < 1 or seat > self.n:
            raise GameError('没有这个座位')
        other = self.seat_map().get(seat)
        if other and other is not p:
            raise GameError('%d号已经有人坐了' % seat)
        if p['seat'] != seat:
            self.sits += 1
            p['sat'] = self.sits                       # 每次有人坐下都换一个编号，「请离座」靠它认人
        p['seat'] = seat

    def a_stand(self, p, data):
        if self.phase != 'lobby':
            raise GameError('游戏已经开始，不能离座')
        p['seat'] = 0

    def a_kick(self, p, data):
        self._need_host(p)
        if self.phase != 'lobby':
            raise GameError('游戏已经开始')
        other = self.seat_map().get(_int(data.get('seat')))
        # 弹出确认框以后，原来的人走了、别人坐了上来（名字可能一样，都叫「玩家」）
        if other and ((data.get('sat') is not None and other.get('sat') != _int(data.get('sat')))
                      or (data.get('name') is not None and other['name'] != data.get('name'))):
            raise GameError('这个座位已经换人了')
        if other:
            other['seat'] = 0
            if not other['online'] and other['id'] != self.host:
                del self.players[other['id']]

    def a_config(self, p, data):
        self._need_host(p)
        if self.phase != 'lobby':
            raise GameError('游戏进行中不能改板子')
        cfg = self.config
        if isinstance(data.get('roles'), dict):
            roles = {}
            for r in ROLE_ORDER:
                v = max(0, min(MAX_SEATS, _int(data['roles'].get(r))))
                roles[r] = v if r in MULTI else min(v, 1)
            if total_of(roles) > MAX_SEATS:
                raise GameError('最多支持 %d 名玩家' % MAX_SEATS)
            if total_of(roles) < 1:
                raise GameError('至少要有 1 张牌')
            cfg['roles'] = roles
        if data.get('witch_self_save') in ('first', 'never', 'always'):
            cfg['witch_self_save'] = data['witch_self_save']
        if data.get('win') in ('side', 'all'):
            cfg['win'] = data['win']
        if 'sheriff' in data:
            cfg['sheriff'] = bool(data['sheriff'])
        n = self.n
        for q in self.players.values():        # 人数变少时，坐在被取消座位上的人站起来
            if q['seat'] > n:
                q['seat'] = 0

    def a_take_host(self, p, data):
        """换一台手机来播报：只有房主掉线了，或者播报卡住了才可以。"""
        host = self.players.get(self.host)
        if host and host['online'] and not (self.stalled and self.cues):
            raise GameError('房主还在线')
        self.host = p['id']
        self.stalled = False
        self.cue_since = time.time()

    def a_test(self, p, data):
        self._need_host(p)
        if self.phase != 'lobby':
            raise GameError('游戏进行中不能试音')
        if not self.cues:
            self.cue(['test'])

    def a_deal(self, p, data):
        self._need_host(p)
        if self.phase != 'lobby':
            raise GameError('已经发过牌了')
        self.owner = p['id']                            # 只在大厅里真正发牌时才换；游戏中途点发牌不算
        err = validate_config(self.config)
        if err:
            raise GameError(err)
        n = self.n
        seated = self.seat_map()
        missing = [s for s in range(1, n + 1) if s not in seated]
        if missing:
            raise GameError('还有 %d 个座位没人坐' % len(missing))
        off = [s for s in range(1, n + 1) if not seated[s]['online']]
        if off:
            raise GameError('%s 掉线了，等他回来或请他离座' % _join(off))
        deck = []
        for r in ROLE_ORDER:
            deck += [r] * self.config['roles'][r]
        self.rng.shuffle(deck)
        self.cues = []
        self.g = {
            'night_no': 0,
            'seats': {s: {'seat': s, 'role': deck[s - 1], 'alive': True, 'cause': None,
                          'can_vote': True, 'shown': None, 'no_gun': False}
                      for s in range(1, n + 1)},
            'seen': set(),
            'notes': {s: [] for s in range(1, n + 1)},
            'pack_met': False,                 # 第一夜「狼人请睁眼」之前，狼人互相不认识
            'witch': {'antidote': True, 'poison': True},
            'guard_last': 0, 'mech_guard_last': 0, 'fear_last': 0, 'dream_last': 0,
            'charm': 0, 'charm_last': 0,
            'swapped': set(),                  # 魔术师已经换过的号码
            'lovers': [], 'third': False,      # third = 人狼恋，情侣和丘比特是第三方
            'model': None,                     # 混血儿的榜样：None = 还没选，0 = 没选（被房主跳过）
            'mech': None,                      # 机械狼学到了什么
            'knight_used': False, 'reflect_used': False,
            'seal_night': 0,                   # 血月使徒自爆后，哪一夜封印神职
            'bm_pending': 0,                   # 被放逐但活到天亮的血月使徒
            'last_exiled': 0,                  # 给守墓人看的：上一个白天被放逐的人
            'sheriff': 0,
            'badge': 'open' if self.config['sheriff'] else 'off',   # open / held / lost / off
            'elect_day': 1,
            'night': None, 'day': None, 'winner': None, 'log': [],
        }
        self.phase = 'deal'
        self.cue(['deal'])

    def a_seen(self, p, data):
        if self.phase != 'deal' or p['seat'] not in self.g['seats']:
            return
        self.g['seen'].add(p['seat'])

    def a_abort(self, p, data):
        """房主结束本局，所有人回到大厅（座位保留）。"""
        self._need_host(p)
        self._to_lobby()

    def a_again(self, p, data):
        self._need_host(p)
        if self.phase != 'over':
            raise GameError('这一局还没结束')
        self._to_lobby()

    def _to_lobby(self):
        self.epoch += 1
        for c in self.claims.values():                 # 回到大厅以后直接选座位就行，还没处理的申请作废
            if c['state'] == 'wait':
                c['state'] = 'no'
        self.cues = []
        self.stalled = False
        self.g = None
        self.phase = 'lobby'

    # ================================================================== 夜晚：流程

    def a_start_night(self, p, data):
        self._need_host(p)
        g = self.g
        if self.phase == 'deal':
            if len(g['seen']) < len(g['seats']) and not data.get('force'):
                raise GameError('还有人没看完身份')
        elif not (self.phase == 'day' and g['day']['stage'] == 'dusk'):
            raise GameError('现在还不能进入黑夜')
        self._start_night()

    def _start_night(self):
        g = self.g
        g['night_no'] += 1
        n = g['night_no']
        self.phase = 'night'
        g['night'] = {
            'steps': night_steps(self.config['roles'], n), 'idx': -1, 'sub': 'fall',
            'sealed': g['seal_night'] == n,    # 今晚神职技能被封印
            'fear': 0,                         # 被梦魇恐惧的人
            'no_kill': False,                  # 狼人被恐惧，今晚不能刀
            'swap': None,                      # 魔术师交换的两个号码
            'dream': 0,                        # 梦游者
            'guard': 0, 'mech_guard': 0,       # 守卫 / 机械狼守的号码
            'guards': [],                      # 实际被守护的人
            'picks': {},                       # 每只狼选的目标 {狼的座位: 目标或0}
            'kill': 0, 'main': 0,              # 狼刀：选的号码 / 实际落到的人
            'extra': 0,                        # 机械狼双刀的第二刀
            'kills': [], 'forced': [],         # 实际被刀的人 / 无视守救的人
            'save': False, 'poisons': [],      # 解药；毒药 [(中毒的人, 下毒的人)]
            'reflect': 0,                      # 触发恶灵骑士反伤、明早出局的人
            'hunt': 0, 'hunt_by': 0,           # 猎魔人狩猎
            'view': {},                        # 正在看的结果卡片 {环节: 卡片}
            'acks': set(), 'log': [], 'deaths': [],
        }
        clips = ['night_fall'] + (['seal'] if g['night']['sealed'] else [])
        self.cue(clips, lambda: self.later(PAUSE_AFTER_NIGHT_FALL, self._next_step))

    def _skip_key(self):
        """当前夜间环节的编号。房主点「跳过」时带上它，免得跳过的是确认框打开之后才轮到的角色。"""
        return '%d-%d' % (self.g['night_no'], self.g['night']['idx'])

    def _step(self):
        nt = self.g['night']
        if 0 <= nt['idx'] < len(nt['steps']):
            return nt['steps'][nt['idx']]
        return None

    def _pack(self):
        """夜里一起睁眼的狼人。"""
        seats = self.g['seats']
        return [s for s in self._alive() if ROLES[seats[s]['role']].get('pack')]

    def _holders(self):
        """今晚握着狼刀的人：有狼群就是狼群，狼群死光了就轮到石像鬼 / 机械狼。"""
        return self._pack() or [s for s in self._alive() if self._team(s) == 'wolf']

    def _actors(self, step):
        seats = self.g['seats']
        if step == 'wolf':
            return self._holders()
        if step == 'lovers':
            return self._alive()
        return [s for s in self._alive() if seats[s]['role'] == step]

    def _blocked(self, seat):
        """这名玩家今晚不能用技能的原因（没有则返回 None）。"""
        nt = self.g['night']
        role = ROLES[self._role(seat)]
        if nt['fear'] == seat:
            return '你今晚被梦魇恐惧了，无法使用技能。'
        if nt['sealed'] and role['team'] == 'good' and role['kind'] == 'god':
            return '血月使徒自爆了，今晚所有神职的技能被封印。'
        return None

    def _rt(self, target):
        """魔术师换了号码以后，对 target 用的技能实际落到谁身上。"""
        sw = self.g['night']['swap']
        if sw and target in sw:
            return sw[1] if target == sw[0] else sw[0]
        return target

    def _next_step(self):
        nt = self.g['night']
        if self.phase != 'night':
            return
        nt['idx'] += 1
        if nt['idx'] >= len(nt['steps']):
            self._finish_night()
            return
        nt['sub'] = 'open'
        self.cue([self._step() + '_open'], self._begin_act)

    def _begin_act(self):
        """「X请睁眼」已经播完：这时才让 X 的手机出现操作界面。"""
        nt = self.g['night']
        step = self._step()
        nt['sub'] = 'act'
        if step == 'wolf':
            self.g['pack_met'] = True
        self.cue([step + '_prompt'])
        if not self._actors(step):
            # 这个角色已经出局：假装他在操作，时长随机
            idx = nt['idx']
            lo, hi = FAKE_ACT.get(step, FAKE_DEFAULT)

            def fake_done():
                if self.g and self.g['night'] is nt and nt['idx'] == idx:
                    self._end_act()
            self.later(self.rng.uniform(lo, hi), fake_done)

    def _end_act(self):
        """操作完成：这时才播「X请闭眼」。"""
        nt = self.g['night']
        if nt['sub'] != 'act':
            return
        nt['sub'] = 'close'
        self.cue([self._step() + '_close'],
                 lambda: self.later(PAUSE_BETWEEN_ROLES, self._next_step))

    def _need_turn(self, p, step):
        """确认现在轮到这名玩家行动，返回他的座位。"""
        if self.phase != 'night':
            raise GameError('现在不是夜晚')
        nt = self.g['night']
        if self._step() != step or nt['sub'] != 'act':
            raise GameError('还没轮到你')
        if p['seat'] not in self._actors(step):
            raise GameError('还没轮到你')
        return p['seat']

    def _pick(self, data, count=1):
        raw = data.get('targets')
        if not isinstance(raw, list):
            raw = [data.get('target')]
        ts = [_int(x) for x in raw if _int(x)]
        if len(ts) != count or len(set(ts)) != count:
            raise GameError('请选择 %d 名玩家' % count)
        for t in ts:
            self._need_alive_target(t)
        return ts

    def _role_label(self, seat):
        """查验具体身份时看到的名字。机械狼学习之后显示成学到的身份。"""
        role = self._role(seat)
        if role == 'mech' and self.g['mech']:
            role = self.g['mech']['role']
        return role

    # ================================================================== 夜晚：各角色的操作

    def a_night(self, p, data):
        """大多数角色共用的入口：选人 / 跳过 / 看完了。"""
        if self.phase != 'night':
            raise GameError('现在不是夜晚')
        nt = self.g['night']
        step = self._step()
        seat = p['seat']
        if nt['sub'] != 'act' or step is None or seat not in self._actors(step):
            raise GameError('还没轮到你')
        if step == 'lovers':
            nt['acks'].add(seat)
            if all(s in nt['acks'] for s in self._actors('lovers')):
                self._end_act()
            return
        if step == 'wolf':
            if not nt['no_kill']:
                raise GameError('请在狼人界面里选择目标')
            self._end_act()
            return
        if step == 'witch':
            if not self._blocked(seat):
                raise GameError('请在女巫界面里操作')
            self._end_act()
            return
        if self._blocked(seat):
            self._end_act()
            return
        getattr(self, '_n_' + step)(seat, data)

    def _n_mixed(self, seat, data):
        g = self.g
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不能选自己做榜样')
        g['model'] = t
        self._note(seat, '你的榜样是 %d号' % t)
        g['night']['log'].append('混血儿选 %d号 做榜样' % t)
        self._end_act()

    def _n_cupid(self, seat, data):
        g = self.g
        a, b = sorted(self._pick(data, 2))
        g['lovers'] = [a, b]
        g['third'] = self._team(a) != self._team(b)     # 混血儿按好人牌算，不看榜样
        g['night']['log'].append('丘比特连 %d号 和 %d号 为情侣%s'
                                 % (a, b, '（人狼恋，第三方）' if g['third'] else ''))
        self._end_act()

    def _n_nightmare(self, seat, data):
        g = self.g
        nt = g['night']
        if data.get('skip'):
            g['fear_last'] = 0
            return self._end_act()
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不能恐惧自己')
        if t == g['fear_last']:
            raise GameError('不能连续两晚恐惧同一名玩家')
        nt['fear'] = t
        g['fear_last'] = t
        if self._team(t) == 'wolf':
            nt['no_kill'] = True
        nt['log'].append('梦魇恐惧 %d号%s' % (t, '（是狼人，今晚不能刀）' if nt['no_kill'] else ''))
        self._end_act()

    def _n_magician(self, seat, data):
        g = self.g
        nt = g['night']
        if data.get('skip'):
            return self._end_act()
        a, b = self._pick(data, 2)
        if a in g['swapped'] or b in g['swapped']:
            raise GameError('每个号码整局只能被交换一次')
        nt['swap'] = (a, b)
        g['swapped'].update((a, b))
        nt['log'].append('魔术师交换 %d号 和 %d号' % (a, b))
        self._end_act()

    def _n_dreamer(self, seat, data):
        nt = self.g['night']
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不能让自己梦游')
        nt['dream'] = self._rt(t)
        nt['log'].append('摄梦人让 %d号 梦游' % t)
        self._end_act()

    def _n_guard(self, seat, data):
        g = self.g
        nt = g['night']
        if data.get('skip'):
            nt['guard'] = 0
            nt['log'].append('守卫空守')
            return self._end_act()
        t = self._pick(data)[0]
        if t == g['guard_last']:
            raise GameError('不能连续两晚守护同一名玩家')
        nt['guard'] = t
        nt['guards'].append(self._rt(t))
        nt['log'].append('守卫守护 %d号' % t)
        self._end_act()

    def _mech_skill(self):
        """机械狼今晚可以主动使用的技能（学到的当晚不能用）。"""
        m = self.g['mech']
        if not m or self.g['night_no'] <= m['night']:
            return None
        if m['role'] in ('psychic', 'gargoyle'):
            return 'exact'
        if m['role'] == 'seer':
            return 'side'
        if m['role'] == 'guard':
            return 'guard'
        if m['role'] == 'witch' and m['poison']:
            return 'poison'
        return None

    def _n_mech(self, seat, data):
        g = self.g
        nt = g['night']
        if 'mech' in nt['view']:
            return self._end_act()
        if g['mech'] is None:
            if data.get('skip'):
                return self._end_act()
            t = self._pick(data)[0]
            if t == seat:
                raise GameError('不能学习自己')
            role = self._role(self._rt(t))
            wolf = ROLES[role]['team'] == 'wolf'
            g['mech'] = {'role': role, 'night': g['night_no'],
                         'poison': role == 'witch', 'double': wolf}
            gain = MECH_DOUBLE if wolf else MECH_GAIN.get(role, '这个身份没有可以学习的技能。')
            nt['view']['mech'] = {'title': '%d号 的身份是' % t, 'big': ROLES[role]['name'],
                                  'tone': 'plain', 'lines': [gain]}
            self._note(seat, '第%d夜学习 %d号：%s' % (g['night_no'], t, ROLES[role]['name']))
            nt['log'].append('机械狼学习 %d号（%s）' % (t, ROLES[role]['name']))
            return
        skill = self._mech_skill()
        if skill is None or data.get('skip'):
            return self._end_act()
        if skill in ('exact', 'side'):
            return self._do_check('mech', seat, data, skill == 'exact')
        t = self._pick(data)[0]
        if skill == 'guard':
            if t == g['mech_guard_last']:
                raise GameError('不能连续两晚守护同一名玩家')
            nt['mech_guard'] = t
            nt['guards'].append(self._rt(t))
            nt['log'].append('机械狼守护 %d号' % t)
        else:
            if t == seat:
                raise GameError('不能毒自己')
            nt['poisons'].append((self._rt(t), seat))
            g['mech']['poison'] = False
            nt['log'].append('机械狼毒 %d号' % t)
        self._end_act()

    def _n_beauty(self, seat, data):
        g = self.g
        nt = g['night']
        if data.get('skip'):
            g['charm_last'] = 0
            return self._end_act()
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不能魅惑自己')
        if t == g['charm_last']:
            raise GameError('不能连续两晚魅惑同一名玩家')
        g['charm'] = self._rt(t)
        g['charm_last'] = t
        nt['log'].append('狼美人魅惑 %d号' % t)
        self._end_act()

    def _do_check(self, step, seat, data, exact):
        """查验：exact 看具体身份，否则只看好人 / 狼人。结果留在屏幕上等他点「看完了」。"""
        g = self.g
        nt = g['night']
        if step in nt['view']:
            return self._end_act()
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不用查验自己')
        actual = self._rt(t)
        if exact:
            label = self._role_label(actual)
            text = ROLES[label]['name']
            tone = 'bad' if ROLES[label]['team'] == 'wolf' else 'good'
        else:
            wolf = self._team(actual) == 'wolf'
            text = '狼人' if wolf else '好人'
            tone = 'bad' if wolf else 'good'
        nt['view'][step] = {'title': '%d号 是' % t, 'big': text, 'tone': tone}
        self._note(seat, '第%d夜查验 %d号：%s' % (g['night_no'], t, text))
        nt['log'].append('%s查验 %d号（%s）' % (step_name(step), t, text))
        if (self._team(seat) == 'good' and self._role(actual) == 'ghostrider'
                and not g['reflect_used'] and not nt['reflect']):
            nt['reflect'] = seat           # 查到恶灵骑士，明早被反伤出局

    def _n_seer(self, seat, data):
        self._do_check('seer', seat, data, False)

    def _n_psychic(self, seat, data):
        self._do_check('psychic', seat, data, True)

    def _n_gargoyle(self, seat, data):
        self._do_check('gargoyle', seat, data, True)

    def _n_gravekeeper(self, seat, data):
        g = self.g
        ex = g['last_exiled']
        if ex:
            self._note(seat, '第%d天被放逐的 %d号：%s'
                       % (g['night_no'] - 1, ex, '狼人' if self._team(ex) == 'wolf' else '好人'))
        self._end_act()

    def _n_witcher(self, seat, data):
        nt = self.g['night']
        if data.get('skip'):
            return self._end_act()
        t = self._pick(data)[0]
        if t == seat:
            raise GameError('不能狩猎自己')
        nt['hunt'] = self._rt(t)
        nt['hunt_by'] = seat
        nt['log'].append('猎魔人狩猎 %d号' % t)
        self._end_act()

    # ---- 狼人

    def _can_double(self, seat):
        """机械狼学了狼人，带刀后有一次双刀。"""
        m = self.g['mech']
        return bool(self._role(seat) == 'mech' and m and m['double']
                    and self.g['night_no'] > m['night'] and seat in self._holders())

    def a_wolf_pick(self, p, data):
        seat = self._need_turn(p, 'wolf')
        nt = self.g['night']
        if nt['no_kill']:
            raise GameError('今晚狼人被恐惧，无法袭击')
        target = _int(data.get('target'))
        if target:
            self._need_alive_target(target)
            if self._role(target) in ('beauty', 'ghostrider'):
                raise GameError('%s 不能被自刀' % ROLES[self._role(target)]['name'])
        nt['picks'][seat] = target

    def a_wolf_extra(self, p, data):
        seat = self._need_turn(p, 'wolf')
        if not self._can_double(seat):
            raise GameError('你没有双刀')
        target = _int(data.get('target'))
        if target:
            self._need_alive_target(target)
        self.g['night']['extra'] = target

    def _wolf_agreed(self):
        """所有握刀的狼选了同一个目标时返回它（0 = 空刀），否则返回 None。"""
        nt = self.g['night']
        wolves = self._holders()
        if not wolves or any(w not in nt['picks'] for w in wolves):
            return None
        picks = set(nt['picks'][w] for w in wolves)
        return picks.pop() if len(picks) == 1 else None

    def a_wolf_confirm(self, p, data):
        self._need_turn(p, 'wolf')
        nt = self.g['night']
        if nt['no_kill']:
            return self._end_act()
        agreed = self._wolf_agreed()
        if agreed is None:
            raise GameError('所有狼人要先选同一个目标')
        self._set_kill(agreed)
        self._end_act()

    def _set_kill(self, agreed):
        g = self.g
        nt = g['night']
        extra = nt['extra']
        if not agreed and extra and g['mech'] and g['mech']['double']:
            # 第一刀空着、只用了「第二刀」：其实就是普通的一刀。女巫照样看得到刀口、可以救，双刀也不算用掉
            agreed, extra = extra, 0
        nt['kill'] = agreed
        nt['main'] = self._rt(agreed) if agreed else 0
        nt['kills'] = [nt['main']] if agreed else []
        nt['log'].append('狼人击杀 %d号' % agreed if agreed else '狼人空刀')
        if extra and g['mech'] and g['mech']['double']:
            e = self._rt(extra)
            if e == nt['main']:
                nt['forced'].append(e)
                nt['log'].append('机械狼双刀同砍 %d号（无视解药和守护）' % extra)
            else:
                nt['kills'].append(e)
                nt['log'].append('机械狼双刀加砍 %d号' % extra)
            g['mech']['double'] = False

    # ---- 女巫

    def _witch_can_save(self, seat):
        g = self.g
        nt = g['night']
        if not g['witch']['antidote'] or not nt['main']:
            return False
        if nt['main'] == seat:
            rule = self.config['witch_self_save']
            return rule == 'always' or (rule == 'first' and g['night_no'] == 1)
        return True

    def a_witch(self, p, data):
        seat = self._need_turn(p, 'witch')
        g = self.g
        nt = g['night']
        if self._blocked(seat):
            return self._end_act()
        save = bool(data.get('save'))
        poison = _int(data.get('poison'))
        if save and poison:
            raise GameError('同一晚不能既用解药又用毒药')
        if save:
            if not self._witch_can_save(seat):
                raise GameError('今晚不能使用解药')
            nt['save'] = True
            g['witch']['antidote'] = False
            nt['log'].append('女巫用解药救 %d号' % nt['main'])
        if poison:
            if not g['witch']['poison']:
                raise GameError('毒药已经用过了')
            if poison == seat:
                raise GameError('不能毒自己')
            self._need_alive_target(poison)
            actual = self._rt(poison)
            nt['poisons'].append((actual, seat))
            g['witch']['poison'] = False
            nt['log'].append('女巫毒 %d号' % poison)
            if (self._role(actual) == 'ghostrider' and not g['reflect_used']
                    and not nt['reflect']):
                nt['reflect'] = seat       # 毒到恶灵骑士，明早被反伤出局
        self._end_act()

    def a_skip(self, p, data):
        """房主强制结束当前夜间环节（有人睡着了、手机没电了）。"""
        self._need_host(p)
        if self.phase != 'night' or self.g['night']['sub'] != 'act':
            raise GameError('现在没有可以跳过的环节')
        if data.get('key') is not None and data.get('key') != self._skip_key():
            raise GameError('那个环节已经结束了')           # 确认框打开以后，流程已经走到下一个角色
        nt = self.g['night']
        if self._step() == 'mixed' and self.g['model'] is None:
            self.g['model'] = 0
        if self._step() == 'wolf' and not nt['no_kill']:
            picks = [nt['picks'][w] for w in self._holders() if w in nt['picks']]
            best = max(picks.count(x) for x in picks) if picks else 0
            tops = sorted(set(x for x in picks if picks.count(x) == best))
            self._set_kill(self.rng.choice(tops) if tops else 0)
        self._end_act()

    # ================================================================== 夜晚：结算

    def _resolve_night(self):
        """根据今晚所有人的操作算出谁倒牌。返回按结算顺序排列的 [{seat, cause}]。"""
        g = self.g
        nt = g['night']
        seats = g['seats']
        order = []

        def dying(s):
            return any(x == s for x, _ in order)

        def die(s, cause):
            if not s or not seats[s]['alive']:
                return
            for i, (x, _) in enumerate(order):
                if x == s:
                    if cause == 'poison':
                        order[i] = (s, 'poison')     # 又被刀又被毒，按被毒算（不能开枪）
                    return
            order.append((s, cause))

        dream = nt['dream']

        def immune(s):                               # 梦游者、恶灵骑士夜里不会死
            return s == dream or seats[s]['role'] == 'ghostrider'

        for k in nt['kills']:
            if immune(k):
                continue
            guarded = k in nt['guards']
            saved = nt['save'] and k == nt['main']
            if guarded == saved:                     # 没守没救 -> 死；同守同救 -> 也死
                die(k, 'wolf')
        for k in nt['forced']:
            if not immune(k):
                die(k, 'wolf')
        for t, _by in nt['poisons']:
            if immune(t) or seats[t]['role'] == 'witcher':
                continue
            die(t, 'poison')
        if nt['reflect'] and not g['reflect_used']:
            g['reflect_used'] = True
            die(nt['reflect'], 'reflect')
        h = nt['hunt']
        if h and not immune(h):
            if ROLES[seats[h]['role']]['team'] == 'wolf':
                die(h, 'hunt')
            else:
                die(nt['hunt_by'], 'backfire')
        if dream and dream == g['dream_last']:
            die(dream, 'dream')                      # 连续两晚梦游

        while True:                                  # 连带出局：摄梦人、情侣、狼美人
            before = len(order)
            if dream and not dying(dream) and any(
                    dying(s) for s in seats if seats[s]['role'] == 'dreamer'):
                die(dream, 'dream')
            if g['lovers']:
                a, b = g['lovers']
                if dying(a) != dying(b):
                    die(b if dying(a) else a, 'love')
            if g['charm'] and any(dying(s) for s in seats if seats[s]['role'] == 'beauty'):
                die(g['charm'], 'charm')
            if len(order) == before:
                break

        g['dream_last'] = dream
        g['guard_last'] = nt['guard']
        g['mech_guard_last'] = nt['mech_guard']
        return [{'seat': s, 'cause': c} for s, c in order]

    def _finish_night(self):
        g = self.g
        nt = g['night']
        nt['sub'] = 'dawn'
        nt['deaths'] = self._resolve_night()
        result = ('倒牌：' + _join(sorted(x['seat'] for x in nt['deaths']))
                  if nt['deaths'] else '平安夜')
        g['log'].append('第%d夜　' % g['night_no'] + '；'.join(nt['log'] + [result]))
        self.cue(['day_break'], self._enter_day)

    # ================================================================== 出局、阵营、胜负

    def _kill(self, seat, cause):
        st = self.g['seats'][seat]
        if st['alive']:
            st['alive'] = False
            st['cause'] = cause

    def _kill_chain(self, seat, cause):
        """白天让一名玩家出局，并处理殉情的连带。返回 ([(座位, 死因)], 获胜方或 None)。"""
        g = self.g
        seats = g['seats']
        out, winner, queue = [], None, [(seat, cause)]
        while queue:
            s, c = queue.pop(0)
            if not seats[s]['alive']:
                continue
            self._kill(s, c)
            out.append((s, c))
            winner = winner or self._check_win()
            if s in g['lovers']:
                other = [x for x in g['lovers'] if x != s][0]
                queue.append((other, 'love'))
            if seats[s]['role'] == 'beauty' and c != 'duel' and g['charm']:
                queue.append((g['charm'], 'charm'))
        return out, winner

    def _say_followers(self, out):
        """播报并记录跟着出局的人（殉情）。"""
        d = self.g['day']
        for s, c in out[1:]:
            line = '%d号 %s，一起出局' % (s, CAUSE_TEXT[c])
            d['feed'].append(line)
            self.g['log'].append('第%d天　%s' % (d['no'], line))
            self.cue(['n%d' % s, 'follow_die'])

    def _camp(self, seat):
        """这名玩家最终算哪一方：good / wolf / third。"""
        g = self.g
        role = self._role(seat)
        if g['third'] and (seat in g['lovers'] or role == 'cupid'):
            return 'third'
        # 混血儿和榜样同输同赢（榜样是第三方，他也是）。被连成情侣的混血儿按情侣的规则算，不再跟随榜样
        if role == 'mixed' and seat not in g['lovers']:
            return self._camp(g['model']) if g['model'] else 'good'   # 榜样不会是他自己，也只有一张混血儿
        if ROLES[role]['team'] == 'wolf':
            return 'wolf'
        if role == 'cupid' and g['lovers'] and all(self._team(s) == 'wolf' for s in g['lovers']):
            return 'wolf'
        return 'good'

    def _check_win(self):
        g = self.g
        seats = g['seats']
        # 混血儿不算神也不算民，也不挡着谁获胜：游戏什么时候结束只看其他人。他自己的输赢看 _camp
        alive = [s for s in self._alive() if seats[s]['role'] != 'mixed']
        if g['third']:
            if all(seats[s]['alive'] for s in g['lovers']):
                # 情侣还在：只剩第三方则他们赢，否则谁都还没赢
                return 'third' if all(self._camp(s) == 'third' for s in alive) else None
        wolves = [s for s in alive if self._team(s) == 'wolf']
        if not wolves:
            return 'good'
        good = [s for s in alive if self._camp(s) == 'good']
        gods = sum(1 for s in good if ROLES[seats[s]['role']]['kind'] == 'god')
        vill = sum(1 for s in good if ROLES[seats[s]['role']]['kind'] == 'villager')
        roles = self.config['roles']
        if self.config['win'] == 'all':
            if gods + vill == 0:
                return 'wolf'
        else:
            has_gods = any(roles[r] for r in GODS)
            has_vill = roles['villager'] > 0
            if (has_gods and gods == 0) or (has_vill and vill == 0):
                return 'wolf'
        return None

    def _ending(self, winner):
        d = self.g['day']
        d['stage'] = 'wait'
        d['settle'] = None
        self.when_quiet(lambda: self._game_over(winner))

    def _game_over(self, winner):
        g = self.g
        g['winner'] = winner
        self.phase = 'over'
        for s in sorted(g['seats']):
            if g['seats'][s]['role'] == 'mixed':
                camp = {'good': '好人阵营', 'wolf': '狼人阵营', 'third': '第三方'}[self._camp(s)]
                why = '被连成情侣' if s in g['lovers'] else (
                    '的榜样是 %d号' % g['model'] if g['model'] else '没有选榜样')
                g['log'].append('混血儿 %d号 %s，属于%s' % (s, why, camp))
        g['log'].append({'good': '好人阵营获胜', 'wolf': '狼人阵营获胜',
                         'third': '情侣阵营（第三方）获胜'}[winner])
        self.cue(['win_' + winner])

    def _can_shoot(self, seat):
        g = self.g
        st = g['seats'][seat]
        gun = st['role'] in ('hunter', 'wolfking') or (
            st['role'] == 'mech' and g['mech'] and g['mech']['role'] == 'hunter')
        return bool(gun and st['cause'] in GUN_OK and not st['no_gun'])

    def _next_alive(self, seat, direction):
        seats = self.g['seats']
        n = len(seats)
        s = seat
        for _ in range(n):
            s = (s - 1 + direction) % n + 1
            if seats[s]['alive']:
                return s
        return seat

    def _ring(self, start, direction, members):
        """从 start 开始按方向绕一圈，把 members 里的人按顺序排出来。"""
        n = len(self.g['seats'])
        out, s = [], start
        for _ in range(n):
            if s in members:
                out.append(s)
            s = (s - 1 + direction) % n + 1
        return out

    # ================================================================== 白天：天亮、警长竞选

    def _enter_day(self):
        g = self.g
        self.phase = 'day'
        g['day'] = {
            'no': g['night_no'], 'stage': 'wait', 'night_deaths': [],
            'feed': [], 'last_words': [], 'speak': None, 'order_opts': None,
            'vote': None, 'results': [], 'pk': [], 'settle': None, 'exiled': 0,
            'elect': None,
            'skip': False,             # 有人自爆 / 骑士决斗成功：今天不发言不投票，直接天黑
            'extra_dead': [],          # 竞选时自爆出局、还没走确认流程的人
        }
        g['last_exiled'] = 0           # 守墓人只看前一个白天的放逐结果
        if self._check_win():
            self._announce()           # 夜里没人死也已经分出胜负（丘比特连完情侣就只剩第三方）：不竞选，直接结束
        elif g['badge'] == 'open' and g['night_no'] == g['elect_day']:
            self._start_election()     # 先竞选警长，再公布昨夜死讯
        else:
            self._announce()

    def _start_election(self):
        d = self.g['day']
        d['stage'] = 'e_signup'
        d['elect'] = {
            'players': self._alive(),  # 昨夜倒牌的人此时还不知道自己出局，照常参加
            'signup': {},              # {座位: 是否上警}
            'all': [], 'cands': [], 'withdrawn': [], 'wd': {},
            'order': [], 'vote': None, 'results': [], 'pk': [], 'voters': [],
        }
        self.cue(['elect_start'])

    def _need_stage(self, *stages):
        if self.phase != 'day' or self.g['day']['stage'] not in stages:
            raise GameError('现在不能这样做')
        return self.g['day']

    def _settled(self, fn):
        """所有人都操作完了：先等语音把话说完，再公布结果，画面不会跑到语音前面。"""
        self.g['day']['stage'] = 'wait'
        self.when_quiet(fn)

    def a_elect_run(self, p, data):
        d = self._need_stage('e_signup')
        e = d['elect']
        seat = p['seat']
        if seat not in e['players']:
            raise GameError('你不能参加竞选')
        if seat in e['signup']:
            raise GameError('你已经选过了')
        e['signup'][seat] = bool(data.get('run'))
        if len(e['signup']) >= len(e['players']):
            self._settled(self._elect_reveal)

    def a_elect_close(self, p, data):
        """房主不等了：没表态的人，按不上警 / 不退水 / 弃票处理。"""
        self._need_host(p)
        d = self._need_stage('e_signup', 'e_withdraw', 'e_vote')
        e = d['elect']
        if d['stage'] == 'e_signup':
            for s in e['players']:
                e['signup'].setdefault(s, False)
            self._settled(self._elect_reveal)
        elif d['stage'] == 'e_withdraw':
            for s in e['cands']:
                e['wd'].setdefault(s, False)
            self._settled(self._elect_after_withdraw)
        else:
            for s in e['vote']['voters']:
                e['vote']['ballots'].setdefault(s, 0)
            self._settled(self._elect_tally)

    def _elect_reveal(self):
        d = self.g['day']
        e = d['elect']
        e['all'] = sorted(s for s, run in e['signup'].items() if run)
        e['cands'] = list(e['all'])
        e['voters'] = [s for s in e['players'] if s not in e['all']]   # 警下
        if not e['cands']:
            d['feed'].append('没有玩家上警')
            self.cue(['elect_none'])
            return self._elect_lost()
        d['feed'].append('上警：' + _join(e['cands']))
        e['order'] = self._ring(self.rng.choice(e['cands']), self.rng.choice([1, -1]), e['cands'])
        d['stage'] = 'e_speech'
        self.cue(['elect_cands'] + ['n%d' % s for s in e['cands']])
        self.cue(['elect_speech'])

    def a_elect_next(self, p, data):
        """房主推进：竞选发言 -> 退水环节；PK 发言 -> PK 投票。"""
        self._need_host(p)
        d = self._need_stage('e_speech', 'e_pk')
        e = d['elect']
        if d['stage'] == 'e_speech':
            d['stage'] = 'e_withdraw'
            e['wd'] = {}
            self.cue(['elect_withdraw'])
        else:
            self._elect_start_vote(2, e['pk'])

    def a_elect_withdraw(self, p, data):
        d = self._need_stage('e_withdraw')
        e = d['elect']
        seat = p['seat']
        if seat not in e['cands']:
            raise GameError('你不在警上')
        if seat in e['wd']:
            raise GameError('你已经选过了')
        e['wd'][seat] = bool(data.get('out'))
        if len(e['wd']) >= len(e['cands']):
            self._settled(self._elect_after_withdraw)

    def _elect_after_withdraw(self):
        d = self.g['day']
        e = d['elect']
        out = sorted(s for s, v in e['wd'].items() if v)
        e['withdrawn'] = out
        e['cands'] = [s for s in e['cands'] if s not in out]
        if out:
            d['feed'].append('退水：' + _join(out))
            self.cue(['n%d' % s for s in out] + ['elect_withdrawn'])
        else:
            d['feed'].append('没有人退水')
            self.cue(['elect_no_withdraw'])
        d['stage'] = 'wait'
        if not e['cands']:
            return self._elect_lost()
        if len(e['cands']) == 1:
            return self._elect_win(e['cands'][0])
        if not e['voters']:
            d['feed'].append('所有人都上警了，警下没有人投票')
            return self._elect_lost()
        self.when_quiet(lambda: self._elect_start_vote(1, e['cands']))

    def _elect_start_vote(self, rnd, cands):
        d = self.g['day']
        e = d['elect']
        d['stage'] = 'e_vote'
        # 第一轮只有警下的人投票；平票 PK 那一轮，退水的人也可以投。
        # 一直留在警上的人（包括没进 PK 的）两轮都不投。
        voters = list(e['voters'])
        if rnd == 2:
            voters = sorted(set(voters) | set(e['withdrawn']))
        e['vote'] = {'round': rnd, 'cands': list(cands), 'voters': voters, 'ballots': {}}
        self.cue(['elect_vote' if rnd == 1 else 'elect_vote_pk'])

    def a_elect_vote(self, p, data):
        d = self._need_stage('e_vote')
        v = d['elect']['vote']
        seat = p['seat']
        if seat not in v['voters']:
            raise GameError('这一轮你不能投票')
        if seat in v['ballots']:
            raise GameError('你已经投过票了')
        target = _int(data.get('target'))
        if target and target not in v['cands']:
            raise GameError('不能投这名玩家')
        v['ballots'][seat] = target
        if len(v['ballots']) >= len(v['voters']):
            self._settled(self._elect_tally)

    def _elect_tally(self):
        g = self.g
        d = g['day']
        e = d['elect']
        v = e['vote']
        counts = {}
        for _voter, target in v['ballots'].items():
            if target:
                counts[target] = counts.get(target, 0) + 1
        best = max(counts.values()) if counts else 0
        top = sorted(s for s, c in counts.items() if c == best)
        e['results'].append({'round': v['round'], 'ballots': dict(v['ballots']),
                             'counts': counts, 'top': top, 'kind': 'elect'})
        e['vote'] = None
        if not top:
            d['feed'].append('警下全部弃票')
            return self._elect_lost()
        if len(top) == 1:
            return self._elect_win(top[0])
        if v['round'] == 1:
            d['stage'] = 'e_pk'
            e['pk'] = top
            e['cands'] = top
            e['order'] = self._ring(self.rng.choice(top), self.rng.choice([1, -1]), top)
            d['feed'].append('警长竞选平票：%s 发言后再投一轮' % _join(top))
            self.cue(['elect_tie'])
        else:
            d['feed'].append('警长竞选再次平票')
            self._elect_lost()

    def _elect_win(self, seat):
        g = self.g
        d = g['day']
        g['sheriff'] = seat
        g['badge'] = 'held'
        d['feed'].append('%d号 当选警长' % seat)
        g['log'].append('第%d天　%d号当选警长' % (d['no'], seat))
        self.cue(['n%d' % seat, 'elect_win'])
        self._elect_end()

    def _elect_lost(self):
        g = self.g
        d = g['day']
        g['badge'] = 'lost'
        d['feed'].append('警徽流失，本局没有警长')
        g['log'].append('第%d天　警徽流失' % d['no'])
        self.cue(['elect_lost'])
        self._elect_end()

    def _elect_end(self):
        d = self.g['day']
        d['stage'] = 'wait'
        self.when_quiet(self._announce)

    # ================================================================== 白天：公布死讯、出局确认

    def _announce(self):
        """公布昨夜死讯。按行动顺序逐个结算，先满足胜利条件的一方获胜。"""
        g = self.g
        nt = g['night']
        d = g['day']
        seats = g['seats']
        d['stage'] = 'wait'
        winner = self._check_win()                     # 天亮之前就已经满足的胜利条件最先算
        died = []
        for x in nt['deaths']:
            if not seats[x['seat']]['alive']:
                continue
            self._kill(x['seat'], x['cause'])
            if x['seat'] == nt['fear']:
                seats[x['seat']]['no_gun'] = True      # 被恐惧的猎人当晚倒牌不能开枪
            died.append(x['seat'])
            winner = winner or self._check_win()
        died.sort()                                    # 按座位号念，不暴露死因
        d['night_deaths'] = died
        if died:
            d['feed'].append('昨夜倒牌：' + _join(died))
            self.cue(['died_last_night'] + ['n%d' % s for s in died])
        else:
            d['feed'].append('昨夜是平安夜')
            self.cue(['peaceful'])
        pend = list(died)
        bm = g['bm_pending']
        if bm:
            g['bm_pending'] = 0
            if seats[bm]['alive'] and not winner:
                out, w = self._kill_chain(bm, 'bm')
                winner = winner or w
                d['feed'].append('%d号（血月使徒）天亮后出局' % bm)
                self.cue(['n%d' % bm, 'bm_die'])
                self._say_followers(out)
                pend += [s for s, _ in out]
        pend += [s for s in d['extra_dead'] if s not in pend]
        if winner:
            return self._ending(winner)
        self.when_quiet(lambda: self._begin_settle(pend, 'night' if d['skip'] else 'discuss'))

    # ---- 出局确认 / 开枪 / 移交警徽。所有出局的人都要在手机上点一下，
    # ---- 这样旁人无法从“谁的手机有动静”看出谁是猎人。

    def _begin_settle(self, seats, then):
        d = self.g['day']
        d['stage'] = 'settle'
        d['settle'] = {'then': then, 'pending': {}, 'words': [], 'done': []}
        for s in seats:
            self._add_settle(s)
        if d['settle']['pending']:
            self.cue(['settle_ask'])
        else:
            self._end_settle()

    def _add_settle(self, seat):
        g = self.g
        g['day']['settle']['pending'][seat] = {
            'can_shoot': self._can_shoot(seat),
            'badge': seat == g['sheriff'],             # 警长出局要决定警徽去向
        }

    def a_settle(self, p, data):
        d = self._need_stage('settle')
        g = self.g
        seat = p['seat']
        pend = d['settle']['pending'].get(seat)
        if not pend:
            raise GameError('现在不需要你确认')
        target = _int(data.get('target'))
        heir = None
        if pend['badge']:
            if data.get('badge') is None:
                raise GameError('请先决定警徽的去向')
            heir = _int(data.get('badge'))
            if heir:
                self._need_alive_target(heir)
        if target:
            if not pend['can_shoot']:
                raise GameError('你无法发动技能')
            self._need_alive_target(target)
        del d['settle']['pending'][seat]
        d['settle']['done'].append(seat)
        if pend['badge']:
            if heir:
                g['sheriff'] = heir
                line = '%d号 把警徽移交给 %d号' % (seat, heir)
                self.cue(['n%d' % seat, 'badge_pass', 'n%d' % heir])
            else:
                g['sheriff'] = 0
                g['badge'] = 'lost'
                line = '%d号 撕掉了警徽' % seat
                self.cue(['n%d' % seat, 'badge_tear'])
            d['feed'].append(line)
            g['log'].append('第%d天　%s' % (d['no'], line))
        if target:
            st = g['seats'][seat]
            st['shown'] = st['role']
            out, winner = self._kill_chain(target, 'shot')
            line = '%d号（%s）发动技能，带走 %d号' % (seat, ROLES[st['role']]['name'], target)
            d['feed'].append(line)
            g['log'].append('第%d天　%s' % (d['no'], line))
            self.cue(['n%d' % seat, 'shoot', 'n%d' % target])
            self._say_followers(out)
            if winner:
                return self._ending(winner)
            d['settle']['words'].append(target)
            for s, _ in out:
                self._add_settle(s)
        if not d['settle']['pending']:
            # 等「请出局的玩家确认」「带走了 X 号」这些话播完，画面再往下走
            d['stage'] = 'wait'
            self.when_quiet(self._end_settle)

    def a_settle_close(self, p, data):
        """房主不等了：还没确认的出局玩家（人走了、手机没电了）一律按「不发动技能」处理，
        其中的警长撕掉警徽。否则一个人不回来，整局就停在这里。"""
        self._need_host(p)
        d = self._need_stage('settle')
        seated = self.seat_map()
        # 只处理房主点「不等了」时屏幕上那几个人。就在这一两秒里刚被猎人带走、刚轮到的人，
        # 还没来得及看手机，不能替他决定不开枪、撕警徽
        saw = data.get('seats')
        saw = None if not isinstance(saw, list) else set(_int(x) for x in saw)
        for seat in sorted(d['settle']['pending']):
            if self.g['day']['stage'] != 'settle' or not self.g['day']['settle']:
                break
            if saw is not None and seat not in saw:
                continue
            self.a_settle(seated[seat], {'target': 0, 'badge': 0})

    def _end_settle(self):
        g = self.g
        d = g['day']
        then = d['settle']['then']
        words = d['settle']['words']
        d['settle'] = None
        if then == 'discuss':
            # 只有第一夜倒牌的人有遗言；白天被带走的人有遗言
            self._begin_discuss((d['night_deaths'] if d['no'] == 1 else []) + words)
        elif then == 'dusk':
            self._begin_dusk(([d['exiled']] if d['exiled'] else []) + words)
        elif then == 'resume':
            d['stage'] = 'discuss'                     # 骑士决斗失败，继续白天
            if d['order_opts']:
                # 警长还没选发言顺序就出局了（骑士警长决斗失败）：按现在的警长重新问一遍，没有警长就随机
                sh = g['sheriff']
                if sh and g['seats'][sh]['alive']:
                    d['order_opts'] = [{'start': self._next_alive(sh, 1), 'dir': 1},
                                       {'start': self._next_alive(sh, -1), 'dir': -1}]
                    self.cue(['order_ask'])
                else:
                    d['order_opts'] = None
                    d['speak'] = {'start': self.rng.choice(self._alive()), 'dir': self.rng.choice([1, -1])}
                    self.cue(['discuss'])
        else:
            d['stage'] = 'wait'
            d['feed'].append('直接进入黑夜')
            self.when_quiet(self._start_night)

    def _begin_discuss(self, words):
        g = self.g
        d = g['day']
        d['stage'] = 'discuss'
        d['last_words'] = list(words)
        if words:
            self.cue(['n%d' % s for s in words] + ['last_words'])
        sh = g['sheriff']
        if sh and g['seats'][sh]['alive']:
            # 警长决定从自己哪一侧开始发言，自己最后发言归票
            d['speak'] = None
            d['order_opts'] = [{'start': self._next_alive(sh, 1), 'dir': 1},
                               {'start': self._next_alive(sh, -1), 'dir': -1}]
            self.cue(['order_ask'])
        else:
            d['speak'] = {'start': self.rng.choice(self._alive()),
                          'dir': self.rng.choice([1, -1])}
            if not words:
                self.cue(['discuss'])

    def a_order(self, p, data):
        d = self._need_stage('discuss')
        g = self.g
        if not p['seat'] or p['seat'] != g['sheriff'] or not d['order_opts']:
            raise GameError('只有警长可以决定发言顺序')
        i = _int(data.get('i'))
        if i not in (0, 1):
            raise GameError('请选择一个发言顺序')
        d['speak'] = d['order_opts'][i]
        d['order_opts'] = None
        self.cue(['discuss'])

    def _begin_dusk(self, words):
        d = self.g['day']
        d['stage'] = 'dusk'
        d['last_words'] = list(words)
        if words:
            self.cue(['n%d' % s for s in words] + ['last_words'])

    # ================================================================== 白天：放逐投票

    def _voters(self):
        seats = self.g['seats']
        return [s for s in self._alive() if seats[s]['can_vote']]

    def a_start_vote(self, p, data):
        self._need_host(p)
        d = self._need_stage('discuss', 'pk')
        g = self.g
        if d['stage'] == 'discuss':
            cands = [s for s in self._alive() if g['seats'][s]['shown'] != 'idiot']
            d['vote'] = {'round': 1, 'cands': cands, 'voters': self._voters(), 'ballots': {}}
        else:
            voters = [s for s in self._voters() if s not in d['pk']]
            if not voters:
                d['feed'].append('没有可以投票的玩家，今天无人出局')
                self.cue(['vote_tie_none'])
                return self._begin_dusk([])
            d['vote'] = {'round': 2, 'cands': list(d['pk']), 'voters': voters, 'ballots': {}}
        d['order_opts'] = None
        d['stage'] = 'vote'
        self.cue(['vote_start'])

    def a_vote(self, p, data):
        d = self._need_stage('vote')
        v = d['vote']
        seat = p['seat']
        if seat not in v['voters']:
            raise GameError('你这一轮没有投票权')
        if seat in v['ballots']:
            raise GameError('你已经投过票了')
        target = _int(data.get('target'))
        if target and target not in v['cands']:
            raise GameError('不能投这名玩家')
        v['ballots'][seat] = target
        if len(v['ballots']) >= len(v['voters']):
            self._settled(self._tally)

    def a_end_vote(self, p, data):
        self._need_host(p)
        d = self._need_stage('vote')
        for s in d['vote']['voters']:
            d['vote']['ballots'].setdefault(s, 0)      # 没投的算弃票
        self._settled(self._tally)

    def _tally(self):
        g = self.g
        d = g['day']
        v = d['vote']
        counts = {}
        for voter, target in v['ballots'].items():
            if target:
                # 警长的一票算 1.5 票
                counts[target] = counts.get(target, 0) + (1.5 if voter == g['sheriff'] else 1)
        best = max(counts.values()) if counts else 0
        top = sorted(s for s, c in counts.items() if c == best)
        d['results'].append({'round': v['round'], 'ballots': dict(v['ballots']),
                             'counts': counts, 'top': top, 'kind': 'exile',
                             'sheriff': g['sheriff']})
        d['vote'] = None
        detail = '；'.join('%d号 %s' % (s, _votes(counts[s])) for s in sorted(counts)) or '全员弃票'
        g['log'].append('第%d天　%s投票：%s' % (d['no'], 'PK' if v['round'] == 2 else '', detail))
        if not top:
            d['feed'].append('无人得票，今天无人出局')
            self.cue(['vote_none'])
            self._begin_dusk([])
        elif len(top) == 1:
            self._exile(top[0])
        elif v['round'] == 1:
            d['stage'] = 'pk'
            d['pk'] = top
            d['feed'].append('平票：%s 发言后再投一轮' % _join(top))
            self.cue(['vote_tie'])
        else:
            d['feed'].append('再次平票，今天无人出局')
            self.cue(['vote_tie_none'])
            self._begin_dusk([])

    def _exile(self, seat):
        g = self.g
        d = g['day']
        st = g['seats'][seat]
        if st['role'] == 'idiot' and st['shown'] != 'idiot':
            st['shown'] = 'idiot'
            st['can_vote'] = False
            line = '%d号 翻牌白痴，免于放逐（之后不能投票）' % seat
            d['feed'].append(line)
            g['log'].append('第%d天　%s' % (d['no'], line))
            self.cue(['n%d' % seat, 'idiot_flip'])
            return self._begin_dusk([])
        g['last_exiled'] = seat
        wolves = [s for s in self._alive() if self._team(s) == 'wolf']
        if st['role'] == 'bloodmoon' and wolves == [seat]:
            # 最后一只狼是血月使徒：翻牌，活到明天天亮
            st['shown'] = 'bloodmoon'
            g['bm_pending'] = seat
            line = '%d号 被放逐，翻牌血月使徒，活到明天天亮后出局' % seat
            d['feed'].append(line)
            g['log'].append('第%d天　%s' % (d['no'], line))
            self.cue(['n%d' % seat, 'bm_delay'])
            return self._begin_dusk([])
        out, winner = self._kill_chain(seat, 'vote')
        d['exiled'] = seat
        d['feed'].append('%d号 被放逐出局' % seat)
        g['log'].append('第%d天　%d号被放逐' % (d['no'], seat))
        self.cue(['n%d' % seat, 'exiled'])
        self._say_followers(out)
        if winner:
            return self._ending(winner)
        d['stage'] = 'wait'
        self.when_quiet(lambda: self._begin_settle([s for s, _ in out], 'dusk'))

    # ================================================================== 白天：自爆、骑士决斗

    def a_boom(self, p, data):
        d = self._need_stage('discuss', 'pk', 'e_speech', 'e_withdraw', 'e_pk')
        g = self.g
        seat = p['seat']
        st = g['seats'].get(seat)
        if not st or not st['alive'] or ROLES[st['role']]['team'] != 'wolf':
            raise GameError('只有存活的狼人可以自爆')
        if not ROLES[st['role']].get('boom'):
            raise GameError('%s 不能自爆' % ROLES[st['role']]['name'])
        target = _int(data.get('target')) if st['role'] == 'whitewolf' else 0
        if target:
            self._need_alive_target(target)
            if target == seat:
                raise GameError('不能带走自己')
        in_election = d['stage'].startswith('e_')

        out, winner = self._kill_chain(seat, 'boom')
        st['shown'] = st['role']
        line = '%d号（%s）自爆' % (seat, ROLES[st['role']]['name'])
        clips = ['n%d' % seat, 'boom']
        if target and not winner:
            out2, winner = self._kill_chain(target, 'take')
            out = out + out2
            line += '，带走 %d号' % target
            clips += ['take', 'n%d' % target]
        d['feed'].append(line)
        g['log'].append('第%d天　%s' % (d['no'], line))
        self.cue(clips)
        for s, c in out:
            if c in ('love', 'charm'):
                self._say_followers([None, (s, c)])
        if st['role'] == 'bloodmoon' and any(self._team(s) == 'wolf' for s in self._alive()):
            g['seal_night'] = g['night_no'] + 1
            d['feed'].append('血月使徒自爆：今晚所有神职的技能被封印')
        if in_election:
            d['elect'] = None
            if g['elect_day'] == 1 and d['no'] == 1:
                g['elect_day'] = 2
                d['feed'].append('警长竞选被打断，推迟到明天')
                self.cue(['elect_postponed'])
            else:
                g['badge'] = 'lost'
                d['feed'].append('警长竞选再次被打断，警徽流失')
                self.cue(['elect_lost'])
        if winner:
            return self._ending(winner)
        d['skip'] = True
        d['stage'] = 'wait'
        dead = [s for s, _ in out]
        if in_election:
            d['extra_dead'] = dead                     # 还没公布昨夜死讯：先公布，再一起确认
            self.when_quiet(self._announce)
        else:
            self.when_quiet(lambda: self._begin_settle(dead, 'night'))

    def a_duel(self, p, data):
        d = self._need_stage('discuss')
        g = self.g
        seat = p['seat']
        st = g['seats'].get(seat)
        if not st or not st['alive'] or st['role'] != 'knight':
            raise GameError('只有存活的骑士可以决斗')
        if g['knight_used']:
            raise GameError('决斗机会已经用过了')
        target = _int(data.get('target'))
        self._need_alive_target(target)
        if target == seat:
            raise GameError('不能和自己决斗')
        g['knight_used'] = True
        st['shown'] = 'knight'
        clips = ['n%d' % seat, 'duel_a', 'n%d' % target, 'duel_b']
        if self._team(target) == 'wolf':
            out, winner = self._kill_chain(target, 'duel')
            line = '%d号 翻牌骑士，决斗 %d号：对方是狼人，出局' % (seat, target)
            self.cue(clips + ['duel_win'])
            then = 'night'
            d['skip'] = True
        else:
            out, winner = self._kill_chain(seat, 'duel_fail')
            line = '%d号 翻牌骑士，决斗 %d号：对方是好人，骑士出局' % (seat, target)
            self.cue(clips + ['duel_lose'])
            then = 'resume'
        d['feed'].append(line)
        g['log'].append('第%d天　%s' % (d['no'], line))
        self._say_followers(out)
        if winner:
            return self._ending(winner)
        d['stage'] = 'wait'
        self.when_quiet(lambda: self._begin_settle([s for s, _ in out], then))

    # ================================================================== 每个人能看到什么

    def view(self, pid):
        """生成某个玩家手机上该显示的全部信息。绝不能包含他不该知道的东西。"""
        p = self.players.get(pid)
        if not p:
            return None
        g = self.g
        n = self.n
        seated = self.seat_map()
        host = self.players.get(self.host)
        over = self.phase == 'over'
        v = {
            'code': self.code, 'phase': self.phase, 'n': n,
            'config': self.config,
            'you': {'id': p['id'], 'name': p['name'], 'seat': p['seat'],
                    'host': p['id'] == self.host},
            'host_seat': host['seat'] if host else 0,
            'host_name': host['name'] if host else '',
            'host_online': bool(host and host['online']),
            'stalled': self.stalled,
            'seats': [],
        }
        count = n if not g else len(g['seats'])
        for s in range(1, count + 1):
            pl = seated.get(s)
            st = g['seats'].get(s) if g else None
            v['seats'].append({
                'seat': s,
                'sat': pl.get('sat', 0) if pl else 0,
                'name': pl['name'] if pl else '',
                'taken': bool(pl),
                'online': bool(pl and pl['online']),
                'host': bool(pl and pl['id'] == self.host),
                'alive': st['alive'] if st else True,
                'can_vote': st['can_vote'] if st else True,
                'shown': (st['role'] if over else st['shown']) if st else None,
                'sheriff': bool(g and g['sheriff'] == s),
            })
        if p['id'] in (self.host, self.owner):
            v['claims'] = [{'rid': c['rid'], 'seat': c['seat'], 'name': c['name']}
                           for c in sorted(self.claims.values(), key=lambda c: c['at'])
                           if self._claim_live(c) and self._may_approve(p, c)]
        if p['id'] == self.host:
            v['cues'] = [{'id': c['id'], 'clips': c['clips'], 'text': cue_text(c['clips'])}
                         for c in self.cues]
            if self.phase == 'night' and g['night']['sub'] == 'act':
                v['skip_key'] = self._skip_key()

        if self.phase == 'lobby':
            v['err'] = validate_config(self.config)
            v['standing'] = sum(1 for q in self.players.values() if not q['seat'])
            return v

        seat = p['seat']
        st = g['seats'].get(seat)
        v['night_no'] = g['night_no']
        v['badge'] = g['badge']
        if st:
            role = ROLES[st['role']]
            me = {'role': st['role'], 'alive': st['alive'], 'team': role['team'],
                  'notes': self._my_notes(seat)}
            if role.get('pack') and g['pack_met']:
                me['mates'] = [{'seat': s, 'role': x['role']}
                               for s, x in sorted(g['seats'].items())
                               if ROLES[x['role']].get('pack') and s != seat]
            v['me'] = me

        if self.phase == 'deal':
            # ready：已经看完身份的座位，所有人都看得到（只是「看没看」，不涉及身份）
            v['deal'] = {'seen': seat in g['seen'], 'count': len(g['seen']), 'ready': sorted(g['seen'])}
        elif self.phase == 'night':
            v['night'] = {'prompt': self._night_prompt(seat, st)}
        elif self.phase == 'day':
            v['day'] = self._day_view(seat, st)
        elif over:
            v['over'] = {'winner': g['winner'], 'log': g['log'], 'lovers': g['lovers'],
                         'third': g['third'], 'model': g['model'] or 0,
                         'camps': {s: self._camp(s) for s in g['seats']},
                         'causes': {s: CAUSE_TEXT.get(x['cause'], '') for s, x in g['seats'].items()
                                    if x['cause']}}
        return v

    def _my_notes(self, seat):
        """按住看身份时显示的私人备忘。"""
        g = self.g
        role = self._role(seat)
        notes = []
        if seat in g['lovers']:
            other = [x for x in g['lovers'] if x != seat][0]
            notes.append('你的情侣是 %d号（%s）' % (other, self._lover_camp()))
        elif role == 'cupid' and g['lovers']:
            notes.append('你连的情侣是 %s（%s）' % (_join(g['lovers']), self._lover_camp()))
        if ROLES[role].get('pack') and not g['pack_met']:
            notes.append('第一夜「狼人请睁眼」时，你会看到同伴是谁')
        if role == 'mixed' and seat in g['lovers']:
            notes.append('你被连成了情侣，按情侣算阵营，不再跟随榜样')
        elif role == 'mixed' and g['model'] == 0:
            notes.append('第一夜没有选榜样，你算好人阵营')
        if role == 'witch':
            notes.append('解药：%s　毒药：%s' % ('还在' if g['witch']['antidote'] else '已用',
                                            '还在' if g['witch']['poison'] else '已用'))
        if role == 'guard' and g['guard_last']:
            notes.append('昨晚守了 %d号' % g['guard_last'])
        if role == 'dreamer' and g['dream_last']:
            notes.append('昨晚的梦游者是 %d号' % g['dream_last'])
        if role == 'nightmare' and g['fear_last']:
            notes.append('昨晚恐惧了 %d号' % g['fear_last'])
        if role == 'beauty' and g['charm']:
            notes.append('现在被你魅惑的是 %d号' % g['charm'])
        if role == 'magician' and g['swapped']:
            notes.append('已经换过的号码：' + _join(sorted(g['swapped'])))
        if role == 'knight':
            notes.append('决斗机会：' + ('已用' if g['knight_used'] else '还在'))
        if role in ('mech', 'gargoyle') and g['night_no']:
            notes.append('其他狼人已经全部出局，由你刀人' if not self._pack()
                         else '其他狼人还在，你现在不能刀人')
        if role == 'mech' and g['mech']:
            m = g['mech']
            if m['role'] == 'witch':
                notes.append('学到的毒药：' + ('还在' if m['poison'] else '已用'))
            if ROLES[m['role']]['team'] == 'wolf':
                notes.append('双刀：' + ('还在' if m['double'] else '已用'))
        return notes + g['notes'][seat]

    def _lover_camp(self):
        g = self.g
        if g['third']:
            return '一好一狼，你们和丘比特是第三方阵营'
        return '同属狼人阵营' if self._team(g['lovers'][0]) == 'wolf' else '同属好人阵营'

    # ---- 夜里轮到自己时，手机上显示什么

    def _pick_prompt(self, step, title, hint, targets, verb, **kw):
        out = {'type': step, 'ui': 'pick', 'title': title, 'hint': hint,
               'targets': targets, 'verb': verb, 'count': 1, 'skip': None, 'tone': 'gold',
               'marks': {}}
        out.update(kw)
        return out

    def _night_prompt(self, seat, st):
        g = self.g
        nt = g['night']
        step = self._step()
        if nt['sub'] != 'act' or not st or not st['alive'] or seat not in self._actors(step):
            return None
        alive = self._alive()
        others = [s for s in alive if s != seat]

        if step == 'lovers':
            if seat in nt['acks']:
                return None
            if seat in g['lovers']:
                other = [x for x in g['lovers'] if x != seat][0]
                lines = ['你的情侣是 %d号。' % other, self._lover_camp() + '。', '你们一人出局，另一人会殉情。']
                if st['role'] == 'mixed':
                    lines.append('你按情侣算阵营，不再跟随榜样。')
                return {'type': step, 'ui': 'info', 'title': '你被选为情侣', 'lines': lines, 'ok': '知道了，闭眼'}
            if st['role'] == 'cupid' and not g['lovers']:
                # 房主把丘比特环节跳过了（丘比特没在手机上选）：这一局没有情侣
                return {'type': step, 'ui': 'info', 'title': '这一局没有情侣',
                        'lines': ['你没有连情侣。点下面的按钮，然后闭眼。'], 'ok': '知道了，闭眼'}
            if st['role'] == 'cupid':
                return {'type': step, 'ui': 'info', 'title': '情侣已经连好',
                        'lines': ['情侣是 %s。' % _join(g['lovers']),
                                  self._lover_camp().replace('你们和丘比特', '他们和你') + '。'],
                        'ok': '知道了，闭眼'}
            return {'type': step, 'ui': 'info', 'title': '你没有被选为情侣',
                    'lines': ['点下面的按钮，然后闭眼。'], 'ok': '知道了，闭眼'}

        if step == 'wolf':
            holders = self._holders()
            if nt['no_kill']:
                return {'type': step, 'ui': 'info', 'title': '今晚无法袭击',
                        'lines': ['有狼人被梦魇恐惧了，今晚狼人不能刀人。'], 'ok': '闭眼'}
            pr = {'type': step, 'ui': 'wolf', 'wolves': holders,
                  'roles': {s: g['seats'][s]['role'] for s in holders},
                  'targets': [s for s in alive
                              if g['seats'][s]['role'] not in ('beauty', 'ghostrider')],
                  'picks': dict(nt['picks']), 'agreed': self._wolf_agreed()}
            if self._can_double(seat):
                pr['double'] = True
                pr['extra'] = nt['extra']
            return pr

        blocked = self._blocked(seat)
        if blocked:
            return {'type': step, 'ui': 'info', 'title': '今晚无法使用技能',
                    'lines': [blocked], 'ok': '闭眼'}
        if step in nt['view']:
            card = dict(nt['view'][step])
            card.update({'type': step, 'ui': 'result', 'ok': '看完了，闭眼'})
            return card

        if step == 'witch':
            w = g['witch']
            return {'type': step, 'ui': 'witch', 'antidote': w['antidote'], 'poison': w['poison'],
                    # 解药用掉以后，女巫不再知道刀口
                    'victim': nt['main'] if w['antidote'] else None,
                    'can_save': self._witch_can_save(seat), 'targets': others}
        if step == 'mixed':
            return self._pick_prompt(step, '混血儿，选一名玩家做榜样', '你和他同一阵营、同输同赢，但看不到他的身份。',
                                     others, '跟随')
        if step == 'cupid':
            return self._pick_prompt(step, '丘比特，选两名玩家成为情侣', '可以选自己。一人出局，另一人殉情。',
                                     alive, '连为情侣', count=2)
        if step == 'nightmare':
            last = g['fear_last']
            return self._pick_prompt(
                step, '梦魇，选一名玩家恐惧', '他今晚无法使用技能。恐惧到狼人的话，今晚狼人不能刀人。'
                + ('昨晚恐惧了 %d号，今晚不能再选他。' % last if last else ''),
                [s for s in others if s != last], '恐惧', skip='今晚不恐惧', tone='red')
        if step == 'magician':
            return self._pick_prompt(
                step, '魔术师，选两名玩家交换号码', '今晚所有对其中一人用的技能，都会落到另一人身上。每个号码整局只能换一次。',
                [s for s in alive if s not in g['swapped']], '交换', count=2, skip='今晚不交换')
        if step == 'dreamer':
            last = g['dream_last']
            return self._pick_prompt(
                step, '摄梦人，选今晚的梦游者', '他今晚免疫狼刀和毒药。'
                + ('昨晚的梦游者是 %d号，再选他会让他死亡。' % last if last else ''),
                others, '让他梦游', marks={last: '昨晚梦游'} if last else {})
        if step == 'guard':
            last = g['guard_last']
            return self._pick_prompt(
                step, '守卫，选一名玩家守护',
                '昨晚守了 %d号，今晚不能再守他。' % last if last else '可以守自己，也可以空守。',
                [s for s in alive if s != last], '守护', skip='空守')
        if step == 'beauty':
            last = g['charm_last']
            return self._pick_prompt(
                step, '狼美人，选一名玩家魅惑', '你出局时，最近被魅惑的人会随你殉情。'
                + ('现在被魅惑的是 %d号。' % g['charm'] if g['charm'] else '')
                + ('今晚不能再选 %d号。' % last if last else ''),
                [s for s in others if s != last], '魅惑', skip='今晚不魅惑', tone='red')
        if step in ('seer', 'psychic', 'gargoyle'):
            what = '好人还是狼人' if step == 'seer' else '具体身份'
            return self._pick_prompt(step, '%s，选一名玩家查验' % ROLES[step]['name'],
                                     '你会立刻看到他的%s。' % what, others, '查验')
        if step == 'gravekeeper':
            ex = g['last_exiled']
            if not ex:
                return {'type': step, 'ui': 'info', 'title': '昨天没有人被放逐',
                        'lines': ['今晚没有信息。'], 'ok': '闭眼'}
            wolf = self._team(ex) == 'wolf'
            return {'type': step, 'ui': 'result', 'title': '昨天被放逐的 %d号 是' % ex,
                    'big': '狼人' if wolf else '好人', 'tone': 'bad' if wolf else 'good',
                    'ok': '看完了，闭眼'}
        if step == 'witcher':
            return self._pick_prompt(step, '猎魔人，是否狩猎一名玩家', '他是狼人则他出局；他是好人则你出局。',
                                     others, '狩猎', skip='今晚不狩猎', tone='red')
        if step == 'mech':
            return self._mech_prompt(seat, alive, others)
        return None

    def _mech_prompt(self, seat, alive, others):
        g = self.g
        knife = ('其他狼人已经全部出局，稍后「狼人请睁眼」时由你刀人。' if not self._pack()
                 else '其他狼人还在，你现在不能刀人。')
        if g['mech'] is None:
            return self._pick_prompt('mech', '机械狼，选一名玩家学习', '整局只能学一次，会得知他的身份并获得技能。' + knife,
                                     others, '学习', skip='今晚不学习')
        skill = self._mech_skill()
        name = ROLES[g['mech']['role']]['name']
        if skill in ('exact', 'side'):
            return self._pick_prompt('mech', '机械狼，选一名玩家查验', '你学到了%s的查验。' % name + knife,
                                     others, '查验', skip='今晚不查验')
        if skill == 'guard':
            last = g['mech_guard_last']
            return self._pick_prompt('mech', '机械狼，选一名玩家守护', '你学到了守卫的守护。' + knife,
                                     [s for s in alive if s != last], '守护', skip='空守')
        if skill == 'poison':
            return self._pick_prompt('mech', '机械狼，是否使用毒药', '你学到了女巫的一瓶毒药。' + knife,
                                     others, '下毒', skip='今晚不用毒', tone='red')
        return {'type': 'mech', 'ui': 'info', 'title': '机械狼',
                'lines': ['你学到的身份是%s。今晚没有需要操作的技能。' % name, knife], 'ok': '闭眼'}

    # ---- 白天的画面

    def _day_view(self, seat, st):
        g = self.g
        d = g['day']
        out = {
            'no': d['no'], 'stage': d['stage'], 'feed': d['feed'],
            'night_deaths': d['night_deaths'], 'last_words': d['last_words'],
            'speak': d['speak'], 'results': d['results'], 'pk': d['pk'],
            'sheriff': g['sheriff'],
        }
        if d['order_opts'] and d['stage'] == 'discuss':
            out['order'] = {'mine': bool(seat) and seat == g['sheriff'], 'opts': d['order_opts']}
        if d['settle']:
            pend = d['settle']['pending']
            mine = pend.get(seat)
            out['settle'] = {'waiting': sorted(pend), 'done': sorted(d['settle']['done']),
                             'mine': dict(mine) if mine else None,
                             'targets': self._alive()}
        if d['vote']:
            vt = d['vote']
            out['vote'] = {'round': vt['round'], 'cands': vt['cands'],
                           'voters': vt['voters'], 'voted': sorted(vt['ballots']),
                           'can': seat in vt['voters'] and seat not in vt['ballots']}
        e = d['elect']
        if e:
            ev = {'players': e['players'], 'all': e['all'], 'cands': e['cands'],
                  'withdrawn': e['withdrawn'], 'order': e['order'], 'pk': e['pk'],
                  'voters': e['voters'], 'results': e['results'], 'mine': None, 'decided': []}
            if d['stage'] == 'e_signup':
                # 举手是同时的：没全部表态之前，只显示谁已经选了，不显示选了什么
                ev['decided'] = sorted(e['signup'])
                if seat in e['players'] and seat not in e['signup']:
                    ev['mine'] = 'signup'
            elif d['stage'] == 'e_withdraw':
                ev['decided'] = sorted(e['wd'])
                if seat in e['cands'] and seat not in e['wd']:
                    ev['mine'] = 'withdraw'
            elif d['stage'] == 'e_vote':
                vt = e['vote']
                ev['vote'] = {'round': vt['round'], 'cands': vt['cands'],
                              'voters': vt['voters'], 'voted': sorted(vt['ballots'])}
                if seat in vt['voters'] and seat not in vt['ballots']:
                    ev['mine'] = 'vote'
            out['elect'] = ev
        return out
