# -*- coding: utf-8 -*-
"""引擎测试。运行： python3 -m unittest discover -s tests"""
import os
import random
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import game  # noqa: E402
from game import GameError, Room  # noqa: E402
from clips import CLIPS  # noqa: E402
from roles import NIGHT_STEPS, PRESETS, ROLE_ORDER, ROLES, full_roles, night_steps  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


class Clock(object):
    """假时钟：定时器不会真的等，由测试决定什么时候触发。"""

    def __init__(self):
        self.now = 0.0
        self.queue = []
        self.seq = 0

    def later(self, sec, fn):
        self.seq += 1
        self.queue.append((self.now + sec, self.seq, fn))

    def run_next(self):
        if not self.queue:
            return False
        self.queue.sort()
        when, _, fn = self.queue.pop(0)
        self.now = when
        fn()
        return True


class FixedRng(object):
    """按指定顺序发牌，其它随机数用带种子的生成器。"""

    def __init__(self, deck=None, seed=0):
        self.deck = deck
        self.r = random.Random(seed)

    def shuffle(self, lst):
        if self.deck:
            assert sorted(lst) == sorted(self.deck), (lst, self.deck)
            lst[:] = self.deck
        else:
            self.r.shuffle(lst)

    def uniform(self, a, b):
        return self.r.uniform(a, b)

    def choice(self, seq):
        return self.r.choice(seq)


# 夜里选人的角色，在 Table.night(...) 里用哪个参数名指定目标
KEY = {'mixed': 'model', 'cupid': 'lovers', 'nightmare': 'fear', 'magician': 'swap', 'dreamer': 'dream',
       'guard': 'guard', 'mech': 'mech', 'beauty': 'charm', 'gargoyle': 'garg',
       'seer': 'check', 'psychic': 'psy', 'witcher': 'hunt'}


class Table(object):
    """一桌人。座位 1 是房主。默认不开警长竞选，专门的测试里再打开。"""

    def __init__(self, deck=None, roles=None, seed=0, sheriff=False, **cfg):
        self.clock = Clock()
        self.room = Room('0000', later=self.clock.later, rng=FixedRng(deck, seed))
        self.heard = []                       # 房主手机已经播完的语音片段
        if roles is None:
            roles = {}
            for r in deck:
                roles[r] = roles.get(r, 0) + 1
        self.pid = {}
        host = self.room.add_player('房主')
        self.room.attach(host['id'])
        self.host = host['id']
        self.room.action(self.host, 'config', dict(cfg, roles=roles, sheriff=sheriff))
        for s in range(1, self.room.n + 1):
            p = host if s == 1 else self.room.add_player('玩家%d' % s)
            if s != 1:
                self.room.attach(p['id'])
            self.pid[s] = p['id']
            self.room.action(p['id'], 'sit', {'seat': s})

    # -- 小工具
    def act(self, who, typ, **data):
        self.room.action(self.pid[who], typ, data)

    def view(self, seat):
        return self.room.view(self.pid[seat])

    def drop(self, seat, after=60):
        """这个座位的手机断线，而且过了很久都没连回来。"""
        now = time.time()
        self.room.detach(self.pid[seat], now=now)
        self.room.sweep(now=now + after)

    @property
    def g(self):
        return self.room.g

    def day(self, seat=1):
        return self.view(seat)['day']

    def stage(self):
        return self.g['day']['stage'] if self.room.phase == 'day' else self.room.phase

    def prompts(self):
        """当前所有玩家手机上的夜间操作界面 {座位: 界面}。"""
        out = {}
        if self.room.phase != 'night':
            return out
        for s in self.pid:
            pr = self.view(s)['night']['prompt']
            if pr:
                out[s] = pr
        return out

    def types(self):
        return {s: p['type'] for s, p in self.prompts().items()}

    def ack_one(self):
        cues = self.view(1).get('cues') or []
        if not cues:
            return False
        self.heard += cues[0]['clips']
        self.room.ack(self.host, cues[0]['id'])
        return True

    def flush(self):
        """把能播的都播完、能到点的定时器都触发，直到需要有人操作为止。"""
        for _ in range(2000):
            if self.ack_one():
                continue
            if self.clock.run_next():
                continue
            return
        raise AssertionError('flush 停不下来')

    def deal(self):
        self.act(1, 'deal')
        for s in self.pid:
            self.act(s, 'seen')
        self.flush()

    def night(self, kill=0, save=False, poison=0, extra=0, **kw):
        """跑完一整夜。没有指定目标的角色：能跳过就跳过，否则选第一个可选的人。"""
        if self.room.phase == 'day':
            self.confirm_dead()
        if self.room.phase != 'night':
            self.act(1, 'start_night')
        self.flush()
        for _ in range(60):
            pr = self.prompts()
            if not pr:
                break
            seat, p = sorted(pr.items())[0]
            typ, ui = p['type'], p['ui']
            if typ == 'lovers':
                for s in pr:
                    self.act(s, 'night', ok=True)
            elif ui in ('info', 'result'):
                self.act(seat, 'night', ok=True)
            elif typ == 'wolf':
                for w in pr:
                    self.act(w, 'wolf_pick', target=kill)
                if extra:
                    self.act([w for w in pr if pr[w].get('double')][0], 'wolf_extra', target=extra)
                self.act(seat, 'wolf_confirm')
            elif typ == 'witch':
                self.act(seat, 'witch', save=save, poison=poison)
            else:
                want = kw.get(KEY[typ])
                if want is None and p['skip']:
                    self.act(seat, 'night', skip=True)
                elif want is None:
                    self.act(seat, 'night', targets=p['targets'][:p['count']])
                else:
                    self.act(seat, 'night', targets=list(want) if isinstance(want, tuple) else [want])
            self.flush()
        assert self.room.phase != 'night', '夜晚没有结束'

    def confirm_dead(self, **shots):
        """出局的人点确认。shots = {座位: 开枪目标}；警长默认撕警徽。"""
        for _ in range(10):
            if self.room.phase != 'day':
                break
            st = (self.day().get('settle') or {})
            if not st.get('waiting'):
                break
            for s in st['waiting']:
                mine = self.day(s)['settle']['mine']
                data = {'target': shots.get(s, 0)}
                if mine['badge']:
                    data['badge'] = shots.get('badge', 0)
                self.act(s, 'settle', **data)
            self.flush()

    def no_exile(self):
        """白天什么都不发生：全员弃票，停在天黑前。"""
        self.confirm_dead()
        self.act(1, 'start_vote')
        self.act(1, 'end_vote')
        self.flush()

    def exile(self, seat):
        self.confirm_dead()
        self.act(1, 'start_vote')
        for s in self.day()['vote']['voters']:
            self.act(s, 'vote', target=seat)
        self.flush()

    def alive(self):
        return [s for s, st in sorted(self.g['seats'].items()) if st['alive']]


# 9 人板：座位 1-3 狼，4-6 民，7 预言家，8 女巫，9 猎人
D9 = ['wolf', 'wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'witch', 'hunter']
# 12 人守卫板：1-4 狼，5-8 民，9 预，10 女，11 猎，12 守
D12 = ['wolf'] * 4 + ['villager'] * 4 + ['seer', 'witch', 'hunter', 'guard']


def board(special_wolf, *gods):
    """12 人板：1-3 狼，4 特殊狼，5-8 民，9-12 四个神。"""
    return ['wolf'] * 3 + [special_wolf] + ['villager'] * 4 + list(gods)


class NightOrderAndSync(unittest.TestCase):
    """语音顺序正确，且手机上的操作界面和语音一一对应。"""

    def test_voice_and_phone_stay_in_step(self):
        t = Table(D12)
        t.deal()
        t.heard = []
        t.act(1, 'start_night')

        # 「天黑请闭眼」还没播完：谁的手机都不该有操作
        self.assertEqual(t.types(), {})
        self.assertTrue(t.ack_one())
        self.assertEqual(t.heard, ['night_fall'])
        self.assertEqual(t.view(1)['cues'], [])            # 停顿中，没有下一句
        self.assertTrue(t.clock.run_next())

        expect = [('guard', [12]), ('wolf', [1, 2, 3, 4]), ('witch', [10]), ('seer', [9])]
        for role, seats in expect:
            # 「X请睁眼」排上了，但还没播完 -> 手机上还没有界面
            self.assertEqual([c['clips'] for c in t.view(1)['cues']], [[role + '_open']])
            self.assertEqual(t.types(), {})
            t.ack_one()
            # 播完了 -> 只有这个角色的手机出现界面，同时开始播操作提示
            self.assertEqual(t.types(), {s: role for s in seats})
            self.assertEqual([c['clips'] for c in t.view(1)['cues']], [[role + '_prompt']])

            # 操作提示还没播完，玩家就操作了：「请闭眼」排在提示后面，不会抢播
            if role == 'guard':
                t.act(12, 'night', targets=[9])
            elif role == 'wolf':
                for w in seats:
                    t.act(w, 'wolf_pick', target=5)
                t.act(2, 'wolf_confirm')
            elif role == 'witch':
                t.act(10, 'witch', save=False, poison=0)
            else:
                t.act(9, 'night', targets=[1])
                self.assertEqual(t.types(), {9: 'seer'})     # 看结果时还睁着眼
                self.assertEqual(t.prompts()[9]['big'], '狼人')
                t.act(9, 'night', ok=True)
            self.assertEqual(t.types(), {})                  # 操作完界面立刻收起
            self.assertEqual([c['clips'] for c in t.view(1)['cues']],
                             [[role + '_prompt'], [role + '_close']])
            t.ack_one()
            t.ack_one()
            self.assertEqual(t.view(1)['cues'], [])          # 两个角色之间有停顿
            self.assertEqual(t.room.phase, 'night')
            t.clock.run_next()

        self.assertEqual([c['clips'] for c in t.view(1)['cues']], [['day_break']])
        self.assertEqual(t.room.phase, 'night')              # 「天亮了」播完才进白天
        t.ack_one()
        self.assertEqual(t.room.phase, 'day')
        self.assertEqual(t.heard, [
            'night_fall',
            'guard_open', 'guard_prompt', 'guard_close',
            'wolf_open', 'wolf_prompt', 'wolf_close',
            'witch_open', 'witch_prompt', 'witch_close',
            'seer_open', 'seer_prompt', 'seer_close',
            'day_break'])

    def test_full_order_with_many_roles(self):
        roles = dict(wolf=2, nightmare=1, beauty=1, gargoyle=1, mech=1, villager=4, seer=1,
                     witch=1, guard=1, psychic=1, gravekeeper=1, dreamer=1, magician=1,
                     witcher=1)
        want = ['nightmare', 'magician', 'dreamer', 'guard', 'mech', 'wolf', 'beauty',
                'gargoyle', 'witch', 'seer', 'psychic']
        self.assertEqual(night_steps(full_roles(roles), 1), want)
        self.assertEqual(night_steps(full_roles(roles), 2), want + ['gravekeeper', 'witcher'])
        cupid = full_roles(dict(wolf=2, villager=2, seer=1, cupid=1))
        self.assertEqual(night_steps(cupid, 1), ['cupid', 'lovers', 'wolf', 'seer'])
        self.assertEqual(night_steps(cupid, 2), ['wolf', 'seer'])

    def test_roles_not_in_board_are_not_called(self):
        t = Table(D9)                                        # 没有守卫
        t.deal()
        t.heard = []
        t.night(kill=4)
        self.assertEqual([c for c in t.heard if c.endswith('_open')],
                         ['wolf_open', 'witch_open', 'seer_open'])

    def test_dead_role_is_still_called_with_fake_delay(self):
        t = Table(D9)
        t.deal()
        t.night(kill=7)                                      # 第一夜刀掉预言家
        t.no_exile()
        t.heard = []
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=4)
        t.act(1, 'wolf_confirm')
        t.flush()
        t.act(8, 'witch', save=False, poison=0)
        # 轮到预言家：语音照念，但没有人的手机出现界面，由定时器假装操作
        for _ in range(20):
            if 'seer_open' in t.heard:
                break
            if not t.ack_one():
                t.clock.run_next()
        self.assertIn('seer_open', t.heard)
        self.assertEqual(t.types(), {})
        before = t.clock.now
        t.flush()
        self.assertGreaterEqual(t.clock.now - before, game.FAKE_DEFAULT[0])
        i = t.heard.index('seer_open')
        self.assertEqual(t.heard[i:i + 4], ['seer_open', 'seer_prompt', 'seer_close', 'day_break'])

    def test_cannot_act_out_of_turn(self):
        t = Table(D12)
        t.deal()
        t.act(1, 'start_night')
        with self.assertRaises(GameError):
            t.act(12, 'night', targets=[1])                  # 语音还没叫到守卫
        t.ack_one()
        t.clock.run_next()
        with self.assertRaises(GameError):
            t.act(12, 'night', targets=[1])                  # 「守卫请睁眼」还没播完
        t.ack_one()
        with self.assertRaises(GameError):
            t.act(9, 'night', targets=[1])                   # 预言家不能抢在守卫环节操作
        with self.assertRaises(GameError):
            t.act(5, 'night', targets=[1])                   # 村民不能冒充守卫
        with self.assertRaises(GameError):
            t.act(1, 'wolf_pick', target=5)                  # 狼人也还没到
        t.act(12, 'night', targets=[1])

    def test_non_host_cannot_ack(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')
        cue_id = t.view(1)['cues'][0]['id']
        t.room.ack(t.pid[2], cue_id)
        self.assertEqual(len(t.view(1)['cues']), 1)
        self.assertNotIn('cues', t.view(2))


class ClassicRules(unittest.TestCase):
    def test_plain_kill_and_empty_knife(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4)
        self.assertEqual(t.day()['night_deaths'], [4])
        t.no_exile()
        t.heard = []
        t.night(kill=0)
        self.assertEqual(t.day()['night_deaths'], [])
        self.assertIn('peaceful', t.heard)

    def test_witch_saves(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4, save=True)
        self.assertEqual(t.alive(), list(range(1, 10)))
        self.assertFalse(t.g['witch']['antidote'])

    def test_guard_rules(self):
        t = Table(D12)
        t.deal()
        t.night(guard=5, kill=5)
        self.assertEqual(t.day()['night_deaths'], [])        # 守住了
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        self.assertNotIn(5, t.prompts()[12]['targets'])      # 不能连守
        with self.assertRaises(GameError):
            t.act(12, 'night', targets=[5])
        t.night(guard=6, kill=6, save=True)
        self.assertEqual(t.day()['night_deaths'], [6])       # 同守同救，照样倒牌
        t.no_exile()
        t.night(guard=7, kill=0, poison=7)
        self.assertEqual(t.day()['night_deaths'], [7])       # 守卫挡不住毒

    def test_witch_cannot_use_both_potions(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=4)
        t.act(1, 'wolf_confirm')
        t.flush()
        with self.assertRaises(GameError):
            t.act(8, 'witch', save=True, poison=1)

    def test_witch_sees_victim_only_while_she_has_antidote(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=4)
        t.act(1, 'wolf_confirm')
        t.flush()
        self.assertEqual(t.prompts()[8]['victim'], 4)
        t.night(save=True)
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=5)
        t.act(1, 'wolf_confirm')
        t.flush()
        pr = t.prompts()[8]
        self.assertIsNone(pr['victim'])
        self.assertFalse(pr['can_save'])

    def _knife_witch(self, night_no, rule):
        t = Table(D9, witch_self_save=rule)
        t.deal()
        if night_no == 2:
            t.night(kill=0)
            t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=8)
        t.act(1, 'wolf_confirm')
        t.flush()
        return t.prompts()[8]['can_save']

    def test_witch_self_save_rules(self):
        self.assertTrue(self._knife_witch(1, 'first'))
        self.assertFalse(self._knife_witch(2, 'first'))
        self.assertFalse(self._knife_witch(1, 'never'))
        self.assertTrue(self._knife_witch(2, 'always'))

    def test_wolves_must_agree(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.act(1, 'wolf_pick', target=4)
        t.act(2, 'wolf_pick', target=5)
        with self.assertRaises(GameError):
            t.act(1, 'wolf_confirm')                         # 3 号还没选
        t.act(3, 'wolf_pick', target=4)
        with self.assertRaises(GameError):
            t.act(1, 'wolf_confirm')                         # 意见不统一
        self.assertIsNone(t.prompts()[1]['agreed'])
        t.act(2, 'wolf_pick', target=4)
        self.assertEqual(t.prompts()[3]['agreed'], 4)
        t.act(3, 'wolf_confirm')
        self.assertEqual(t.g['night']['kill'], 4)

    def test_hunter_knifed_can_shoot_poisoned_cannot(self):
        t = Table(D9)
        t.deal()
        t.heard = []
        t.night(kill=9)
        self.assertEqual(t.stage(), 'settle')
        self.assertTrue(t.day(9)['settle']['mine']['can_shoot'])
        t.act(9, 'settle', target=1)
        t.flush()
        self.assertFalse(t.g['seats'][1]['alive'])
        self.assertEqual(t.view(4)['seats'][8]['shown'], 'hunter')
        self.assertIn('shoot', t.heard)
        self.assertEqual(t.day()['settle']['waiting'], [1])  # 被带走的人也要确认
        t.act(1, 'settle', target=0)
        t.flush()
        self.assertEqual(t.stage(), 'discuss')
        self.assertEqual(t.day()['last_words'], [9, 1])

        t = Table(D9)
        t.deal()
        t.night(kill=4, poison=9)
        self.assertFalse(t.day(9)['settle']['mine']['can_shoot'])
        with self.assertRaises(GameError):
            t.act(9, 'settle', target=1)
        # 旁人看到的只是“等待 4号、9号 确认”，看不出谁能开枪
        self.assertEqual(t.day(5)['settle']['waiting'], [4, 9])
        self.assertIsNone(t.day(5)['settle']['mine'])

    def test_vote_exile_and_last_words(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4)
        t.confirm_dead()
        t.act(1, 'start_vote')
        self.assertFalse(t.day(4)['vote']['can'])            # 死人不能投
        for s in (1, 2, 3):
            t.act(s, 'vote', target=5)
        for s in (5, 6, 7, 8):
            t.act(s, 'vote', target=1)
        self.assertEqual(t.stage(), 'vote')                  # 9 号还没投
        with self.assertRaises(GameError):
            t.act(1, 'vote', target=6)                       # 不能改票
        t.act(9, 'vote', target=0)
        t.flush()
        self.assertFalse(t.g['seats'][1]['alive'])
        res = t.day(2)['results'][0]
        self.assertEqual(res['top'], [1])
        self.assertEqual(res['counts'], {1: 4, 5: 3})
        t.confirm_dead()
        self.assertEqual(t.stage(), 'dusk')
        self.assertEqual(t.day()['last_words'], [1])

    def test_tie_then_pk_then_no_exile(self):
        t = Table(D9)
        t.deal()
        t.heard = []
        t.night(kill=0)
        t.act(1, 'start_vote')
        for s in (1, 2, 3, 4):
            t.act(s, 'vote', target=5)
        for s in (5, 6, 7, 8):
            t.act(s, 'vote', target=1)
        t.act(9, 'vote', target=0)
        t.flush()
        self.assertEqual((t.stage(), t.day()['pk']), ('pk', [1, 5]))
        t.act(1, 'start_vote')
        v = t.day(2)['vote']
        self.assertEqual((v['round'], v['cands']), (2, [1, 5]))
        self.assertNotIn(1, v['voters'])                     # PK 台上的人不投票
        with self.assertRaises(GameError):
            t.act(2, 'vote', target=6)                       # 只能投 PK 台上的人
        for s in (2, 3, 4):
            t.act(s, 'vote', target=5)
        for s in (6, 7, 8):
            t.act(s, 'vote', target=1)
        t.act(9, 'vote', target=0)
        t.flush()
        self.assertEqual(t.stage(), 'dusk')
        self.assertEqual(t.alive(), list(range(1, 10)))
        self.assertIn('vote_tie', t.heard)
        self.assertIn('vote_tie_none', t.heard)

    def test_idiot_survives_exile_but_loses_vote(self):
        t = Table(['wolf'] * 4 + ['villager'] * 4 + ['seer', 'witch', 'hunter', 'idiot'])
        t.deal()
        t.night(kill=0)
        t.exile(12)
        self.assertTrue(t.g['seats'][12]['alive'])
        self.assertEqual(t.view(1)['seats'][11]['shown'], 'idiot')
        self.assertEqual(t.stage(), 'dusk')
        t.night(kill=0)
        t.act(1, 'start_vote')
        v = t.day(12)['vote']
        self.assertFalse(v['can'])
        self.assertNotIn(12, v['cands'])                     # 翻牌后不能再被投

    def test_wolf_boom_goes_straight_to_night(self):
        t = Table(D9)
        t.deal()
        t.night(kill=0)
        with self.assertRaises(GameError):
            t.act(5, 'boom')                                 # 好人不能自爆
        t.heard = []
        t.act(2, 'boom')
        self.assertEqual(t.view(5)['seats'][1]['shown'], 'wolf')
        self.assertEqual(t.room.phase, 'day')                # 等「自爆」播完
        t.flush()
        t.confirm_dead()                                     # 自爆的人确认后才天黑
        self.assertEqual(t.heard[:2], ['n2', 'boom'])
        self.assertEqual(t.room.phase, 'night')
        self.assertEqual(t.g['night_no'], 2)

    def test_wolfking_shoots_when_exiled(self):
        t = Table(['wolfking', 'wolf', 'wolf', 'villager', 'villager', 'villager',
                   'seer', 'witch', 'hunter'])
        t.deal()
        t.night(kill=0)
        t.exile(1)
        self.assertTrue(t.day(1)['settle']['mine']['can_shoot'])
        t.act(1, 'settle', target=7)
        t.flush()
        self.assertFalse(t.g['seats'][7]['alive'])


class Winning(unittest.TestCase):
    def test_good_wins_when_all_wolves_out(self):
        deck = ['wolf', 'villager', 'villager', 'seer']
        t = Table(deck)
        t.deal()
        t.heard = []
        t.night(kill=0)
        t.act(1, 'start_vote')
        for s in (1, 2, 3, 4):
            t.act(s, 'vote', target=1)
        self.assertEqual(t.room.phase, 'day')                # 先播完放逐，再宣布结果
        t.flush()
        self.assertEqual(t.room.phase, 'over')
        self.assertEqual(t.view(2)['over']['winner'], 'good')
        self.assertEqual(t.heard[-3:], ['n1', 'exiled', 'win_good'])
        self.assertEqual([s['shown'] for s in t.view(2)['seats']], deck)   # 结束后全员亮牌

    def test_wolves_win_by_killing_one_side(self):
        deck = ['wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'witch']
        t = Table(deck)
        t.deal()
        t.night(kill=6)                                      # 刀预言家
        t.no_exile()
        t.night(kill=7)                                      # 刀女巫 -> 神全灭
        self.assertEqual(t.view(3)['over']['winner'], 'wolf')

        t = Table(deck, win='all')
        t.deal()
        t.night(kill=6)
        t.no_exile()
        t.night(kill=7)
        self.assertEqual(t.room.phase, 'day')                # 屠城：神死光还不算赢

    def test_last_god_hunter_dies_game_ends_before_shot(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'villager', 'hunter'])
        t.deal()
        t.night(kill=6)
        self.assertEqual(t.view(1)['over']['winner'], 'wolf')


class NewWolves(unittest.TestCase):
    def test_white_wolf_takes_someone_when_booming(self):
        t = Table(board('whitewolf', 'seer', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0)
        with self.assertRaises(GameError):
            t.act(4, 'boom', target=4)
        t.act(4, 'boom', target=11)                          # 带走猎人
        t.flush()
        self.assertEqual(t.alive(), [1, 2, 3, 5, 6, 7, 8, 9, 10, 12])
        self.assertTrue(t.day(11)['settle']['mine']['can_shoot'])   # 被带走的猎人可以开枪
        t.confirm_dead(**{'11': 0})
        self.assertEqual(t.room.phase, 'night')

    def test_ordinary_wolf_cannot_take_anyone(self):
        t = Table(D9)
        t.deal()
        t.night(kill=0)
        t.act(2, 'boom', target=7)
        t.flush()
        self.assertTrue(t.g['seats'][7]['alive'])

    def test_wolf_beauty_charm(self):
        t = Table(board('beauty', 'seer', 'witch', 'knight', 'guard'))
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        with self.assertRaises(GameError):
            t.act(1, 'wolf_pick', target=4)                  # 狼美人不能被自刀
        t.night(kill=0, charm=9)
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        t.night(kill=0)
        self.assertEqual(t.g['charm'], 9)                    # 今晚没魅惑，沿用上一次的
        with self.assertRaises(GameError):
            t.act(4, 'boom')                                 # 狼美人不能自爆
        t.exile(4)
        self.assertEqual(t.alive(), [1, 2, 3, 5, 6, 7, 8, 10, 11, 12])   # 9 号殉情
        self.assertEqual(t.g['seats'][9]['cause'], 'charm')

    def test_beauty_cannot_charm_same_player_twice_in_a_row(self):
        t = Table(board('beauty', 'seer', 'witch', 'knight', 'guard'))
        t.deal()
        t.night(kill=0, charm=9)
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        for w in (1, 2, 3, 4):
            t.act(w, 'wolf_pick', target=0)
        t.act(1, 'wolf_confirm')
        t.flush()
        self.assertNotIn(9, t.prompts()[4]['targets'])
        with self.assertRaises(GameError):
            t.act(4, 'night', targets=[9])

    def test_knight_duel(self):
        t = Table(board('beauty', 'seer', 'witch', 'knight', 'guard'))
        t.deal()
        t.night(kill=0, charm=9)
        with self.assertRaises(GameError):
            t.act(9, 'duel', target=4)                       # 不是骑士
        t.heard = []
        t.act(11, 'duel', target=4)                          # 决斗狼美人
        t.flush()
        self.assertFalse(t.g['seats'][4]['alive'])
        self.assertTrue(t.g['seats'][9]['alive'])            # 被决斗出局，不带走被魅惑的人
        self.assertEqual(t.view(1)['seats'][10]['shown'], 'knight')
        self.assertIn('duel_win', t.heard)
        t.confirm_dead()
        self.assertEqual(t.room.phase, 'night')              # 决斗成功直接天黑
        t.night(kill=0)
        with self.assertRaises(GameError):
            t.act(11, 'duel', target=1)                      # 只有一次

        t = Table(board('beauty', 'seer', 'witch', 'knight', 'guard'))
        t.deal()
        t.night(kill=0)
        t.act(11, 'duel', target=5)                          # 决斗到好人
        t.flush()
        self.assertFalse(t.g['seats'][11]['alive'])
        self.assertTrue(t.g['seats'][5]['alive'])
        t.confirm_dead()
        self.assertEqual(t.stage(), 'discuss')               # 白天继续

    def test_gargoyle(self):
        t = Table(board('gargoyle', 'seer', 'witch', 'hunter', 'gravekeeper'))
        t.deal()
        self.assertNotIn('mates', t.view(4)['me'])           # 石像鬼不认识狼队友
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(sorted(t.types()), [1, 2, 3])       # 狼人睁眼时没有石像鬼
        self.assertEqual([m['seat'] for m in t.view(1)['me']['mates']], [2, 3])
        t.night(kill=0, garg=10, check=4)
        self.assertIn('第1夜查验 10号：女巫', t.view(4)['me']['notes'])
        self.assertIn('第1夜查验 4号：狼人', t.view(9)['me']['notes'])   # 预言家验石像鬼是狼
        for w in (1, 2, 3):                                  # 狼队友全部出局
            t.exile(w)
            if w != 3:
                t.night(kill=0)
        t.confirm_dead()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {4: 'wolf'})             # 轮到石像鬼刀人
        t.night(kill=5)
        self.assertEqual(t.day()['night_deaths'], [5])

    def test_gravekeeper_learns_side_of_exiled_player(self):
        t = Table(board('gargoyle', 'seer', 'witch', 'hunter', 'gravekeeper'))
        t.deal()
        t.heard = []
        t.night(kill=0)
        self.assertNotIn('gravekeeper_open', t.heard)        # 第一夜没有守墓人环节
        t.exile(2)
        t.confirm_dead()
        t.act(1, 'start_night')
        t.flush()
        for _ in range(8):
            pr = t.prompts()
            if 12 in pr:
                break
            seat, p = sorted(pr.items())[0]
            if p['type'] == 'wolf':
                for w in pr:
                    t.act(w, 'wolf_pick', target=0)
                t.act(seat, 'wolf_confirm')
            elif p['type'] == 'witch':
                t.act(seat, 'witch')
            elif p['ui'] == 'pick':
                t.act(seat, 'night', targets=p['targets'][:1])
            else:
                t.act(seat, 'night', ok=True)
            t.flush()
        self.assertEqual(t.prompts()[12]['big'], '狼人')
        t.night(kill=0)
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        t.night(kill=0)
        self.assertIn('第1天被放逐的 2号：狼人', t.view(12)['me']['notes'])
        self.assertEqual(len([n for n in t.view(12)['me']['notes'] if '被放逐' in n]), 1)

    def test_mech_wolf_learns_and_disguises(self):
        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)                        # 守卫
        t.flush()
        self.assertEqual(t.types(), {4: 'mech'})
        t.act(4, 'night', skip=True)                         # 第一夜先不学
        t.flush()
        self.assertEqual(sorted(t.types()), [1, 2, 3])       # 机械狼不和狼人一起睁眼
        t.night(kill=0, psy=4)
        self.assertIn('第1夜查验 4号：机械狼', t.view(9)['me']['notes'])
        t.no_exile()
        t.night(kill=0, mech=10, psy=4)                      # 学女巫
        self.assertIn('第2夜学习 10号：女巫', t.view(4)['me']['notes'])
        self.assertIn('第2夜查验 4号：女巫', t.view(9)['me']['notes'])   # 学了以后显示成女巫
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        pr = t.prompts()[4]
        self.assertEqual((pr['verb'], pr['tone']), ('下毒', 'red'))
        t.night(kill=0, mech=9)                              # 用学来的毒药
        self.assertEqual(t.day()['night_deaths'], [9])
        self.assertFalse(t.g['mech']['poison'])

    def test_mech_wolf_gets_the_knife_and_double_kill(self):
        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, mech=1)                              # 学到狼人：一次双刀
        for w in (1, 2, 3):
            t.exile(w)
            if w != 3:
                t.night(kill=0)
        t.confirm_dead()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', targets=[5])                      # 守卫守 5
        t.flush()
        t.act(4, 'night', ok=True)                           # 机械狼环节：没有主动技能
        t.flush()
        self.assertEqual(t.types(), {4: 'wolf'})
        self.assertTrue(t.prompts()[4]['double'])
        t.act(4, 'wolf_pick', target=5)
        t.act(4, 'wolf_extra', target=5)                     # 两刀砍同一人
        t.act(4, 'wolf_confirm')
        t.flush()
        t.night(save=True)                                   # 女巫还救了
        self.assertEqual(t.day()['night_deaths'], [5])       # 无视守护和解药
        self.assertFalse(t.g['mech']['double'])

        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, mech=1)
        for w in (1, 2, 3):
            t.exile(w)
            if w != 3:
                t.night(kill=0)
        t.night(kill=5, extra=6)
        self.assertEqual(t.day()['night_deaths'], [5, 6])    # 一晚刀两个

    def test_mech_wolf_learns_hunter_and_shoots(self):
        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, mech=11)
        t.exile(4)
        self.assertTrue(t.day(4)['settle']['mine']['can_shoot'])

    def test_nightmare(self):
        t = Table(board('nightmare', 'seer', 'witch', 'hunter', 'guard'))
        t.deal()
        self.assertNotIn('mates', t.view(4)['me'])           # 第一夜恐惧前不认识队友
        self.assertNotIn('mates', t.view(1)['me'])
        t.heard = []
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {4: 'nightmare'})        # 梦魇最先睁眼
        t.act(4, 'night', targets=[9])                       # 恐惧预言家
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        self.assertEqual(len(t.view(4)['me']['mates']), 3)   # 狼人睁眼后认识了
        for w in (1, 2, 3, 4):
            t.act(w, 'wolf_pick', target=5)
        t.act(1, 'wolf_confirm')
        t.flush()
        t.act(10, 'witch')
        t.flush()
        pr = t.prompts()[9]
        self.assertEqual(pr['ui'], 'info')                   # 预言家被恐惧，不能查验
        t.act(9, 'night', targets=[1])                       # 就算硬发请求也不会查验
        t.flush()
        self.assertEqual(t.g['notes'][9], [])
        self.assertEqual(t.heard.index('nightmare_open'), 1)

        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        self.assertNotIn(9, t.prompts()[4]['targets'])       # 不能连续恐惧同一人
        t.act(4, 'night', targets=[2])                       # 恐惧到狼队友
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        self.assertEqual(t.prompts()[1]['ui'], 'info')       # 今晚狼人不能刀
        with self.assertRaises(GameError):
            t.act(1, 'wolf_pick', target=5)
        t.night()
        self.assertEqual(t.day()['night_deaths'], [])

    def test_feared_hunter_cannot_shoot_that_night(self):
        t = Table(board('nightmare', 'seer', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(fear=11, kill=11)
        self.assertFalse(t.day(11)['settle']['mine']['can_shoot'])

    def test_ghost_rider_reflects_once(self):
        t = Table(board('ghostrider', 'seer', 'witch', 'hunter', 'guard'))
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)
        t.flush()
        with self.assertRaises(GameError):
            t.act(1, 'wolf_pick', target=4)                  # 不能自刀恶灵骑士
        t.night(kill=0, check=4)
        self.assertIn('第1夜查验 4号：狼人', t.view(9)['me']['notes'])
        self.assertEqual(t.day()['night_deaths'], [9])       # 预言家被反伤
        t.no_exile()
        t.night(kill=0, poison=4)
        self.assertEqual(t.day()['night_deaths'], [])        # 反伤只有一次；毒药对他无效
        self.assertTrue(t.g['seats'][4]['alive'])
        with self.assertRaises(GameError):
            t.act(4, 'boom')

    def test_ghost_rider_reflects_poison(self):
        t = Table(board('ghostrider', 'seer', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, poison=4, check=1)
        self.assertEqual(t.day()['night_deaths'], [10])      # 女巫被反伤，恶灵骑士没事

    def test_blood_moon_boom_seals_gods(self):
        t = Table(board('bloodmoon', 'seer', 'witch', 'idiot', 'witcher'))
        t.deal()
        t.night(kill=0)
        t.act(4, 'boom')
        t.flush()
        t.heard = []
        t.confirm_dead()
        self.assertEqual(t.room.phase, 'night')
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=5)
        t.act(1, 'wolf_confirm')
        t.flush()
        self.assertEqual(t.prompts()[10]['ui'], 'info')      # 女巫被封印
        t.act(10, 'witch', save=True)                        # 发了也没用
        t.flush()
        self.assertTrue(t.g['witch']['antidote'])
        t.night()
        self.assertEqual(t.day()['night_deaths'], [5])
        self.assertIn('seal', t.heard)
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        for w in (1, 2, 3):
            t.act(w, 'wolf_pick', target=6)
        t.act(1, 'wolf_confirm')
        t.flush()
        self.assertEqual(t.prompts()[10]['ui'], 'witch')     # 只封印一晚

    def test_blood_moon_last_wolf_lives_until_dawn(self):
        t = Table(['bloodmoon', 'villager', 'villager', 'villager', 'seer', 'witch'])
        t.deal()
        t.night(kill=0)
        t.exile(1)
        self.assertTrue(t.g['seats'][1]['alive'])            # 被放逐但还活着
        self.assertEqual(t.view(2)['seats'][0]['shown'], 'bloodmoon')
        self.assertEqual(t.stage(), 'dusk')
        t.night(kill=2)                                      # 还能再刀一晚
        self.assertEqual(t.view(3)['over']['winner'], 'good')
        self.assertEqual(t.g['seats'][1]['cause'], 'bm')
        self.assertFalse(t.g['seats'][2]['alive'])

    def test_blood_moon_last_night_kill_can_still_win(self):
        t = Table(['bloodmoon', 'villager', 'villager', 'villager', 'seer'])
        t.deal()
        t.night(kill=0)
        t.exile(1)
        t.night(kill=5)                                      # 刀掉唯一的神 -> 屠边
        self.assertEqual(t.view(3)['over']['winner'], 'wolf')


class NewGods(unittest.TestCase):
    def test_psychic_sees_exact_role(self):
        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, psy=11)
        self.assertIn('第1夜查验 11号：猎人', t.view(9)['me']['notes'])

    def test_witcher(self):
        t = Table(board('bloodmoon', 'seer', 'witch', 'idiot', 'witcher'))
        t.deal()
        t.heard = []
        t.night(kill=0, poison=12)
        self.assertNotIn('witcher_open', t.heard)            # 第一夜不能狩猎
        self.assertEqual(t.day()['night_deaths'], [])        # 毒药对猎魔人无效
        t.no_exile()
        t.night(kill=0, hunt=2)
        self.assertEqual(t.day()['night_deaths'], [2])       # 狩猎到狼人
        t.no_exile()
        t.night(kill=0, hunt=5)
        self.assertEqual(t.day()['night_deaths'], [12])      # 狩猎到好人，自己出局
        self.assertEqual(t.g['seats'][12]['cause'], 'backfire')

    def test_dreamer(self):
        t = Table(board('wolfking', 'seer', 'witch', 'hunter', 'dreamer'))
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        pr = t.prompts()[12]
        self.assertIsNone(pr['skip'])                        # 必须选人
        self.assertNotIn(12, pr['targets'])
        t.night(dream=5, kill=5)
        self.assertEqual(t.day()['night_deaths'], [])        # 梦游者免疫狼刀
        t.no_exile()
        t.night(dream=6, kill=0, poison=6)
        self.assertEqual(t.day()['night_deaths'], [])        # 也免疫毒药
        t.no_exile()
        t.night(dream=6, kill=0)
        self.assertEqual(t.day()['night_deaths'], [6])       # 连续两晚梦游而死
        self.assertEqual(t.g['seats'][6]['cause'], 'dream')

    def test_dreamer_dies_with_dreamwalker(self):
        t = Table(board('wolfking', 'seer', 'witch', 'hunter', 'dreamer'))
        t.deal()
        t.night(dream=11, kill=12)                           # 摄梦人被刀
        self.assertEqual(t.day()['night_deaths'], [11, 12])  # 梦游者一起倒牌
        self.assertFalse(t.day(11)['settle']['mine']['can_shoot'])   # 梦死的猎人不能开枪

    def test_magician_swap_redirects_everything(self):
        t = Table(board('wolfking', 'seer', 'witch', 'hunter', 'magician'))
        t.deal()
        t.night(swap=(5, 1), kill=5, check=5)
        self.assertEqual(t.day()['night_deaths'], [1])       # 刀 5 号，倒的是 1 号
        self.assertIn('第1夜查验 5号：狼人', t.view(9)['me']['notes'])   # 验 5 号，看到的是 1 号
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        pr = t.prompts()[12]
        self.assertNotIn(5, pr['targets'])                   # 号码整局只能换一次
        self.assertNotIn(1, pr['targets'])
        with self.assertRaises(GameError):
            t.act(12, 'night', targets=[5, 6])
        t.night(kill=6)
        self.assertEqual(t.day()['night_deaths'], [6])       # 交换只管当晚


class Cupid(unittest.TestCase):
    D = ['wolf'] * 4 + ['villager'] * 4 + ['seer', 'witch', 'hunter', 'cupid']

    def test_lovers_see_each_other_and_die_together(self):
        t = Table(self.D)
        t.deal()
        t.heard = []
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {12: 'cupid'})           # 丘比特第一夜最先行动
        t.act(12, 'night', targets=[5, 11])
        t.flush()
        self.assertEqual(len(t.types()), 12)                 # 所有人睁眼看手机
        self.assertIn('11号', t.prompts()[5]['lines'][0])
        self.assertEqual(t.prompts()[6]['title'], '你没有被选为情侣')
        self.assertNotIn('5号', repr(t.view(6)))
        t.night(kill=5)
        self.assertEqual(t.day()['night_deaths'], [5, 11])   # 猎人殉情
        self.assertFalse(t.day(11)['settle']['mine']['can_shoot'])   # 殉情不能开枪
        self.assertEqual(t.heard[:8], ['night_fall', 'cupid_open', 'cupid_prompt', 'cupid_close',
                                       'lovers_open', 'lovers_prompt', 'lovers_close', 'wolf_open'])
        t.no_exile()
        t.heard = []
        t.night(kill=0)
        self.assertNotIn('cupid_open', t.heard)              # 只有第一夜

    def test_host_skipping_cupid_leaves_no_lovers_and_nobody_stuck(self):
        """丘比特一直不选，房主跳过：这一局没有情侣。丘比特自己的画面不能因此出错（他要是房主，播报就停了）。"""
        t = Table(['cupid'] + ['wolf'] * 4 + ['villager'] * 4 + ['seer', 'witch', 'hunter'])    # 房主就是丘比特
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {1: 'cupid'})
        t.act(1, 'skip')
        t.flush()
        self.assertEqual(len(t.types()), 12)                 # 情侣确认环节照常进行，看不出有没有连
        for s in t.pid:
            t.view(s)                                        # 每个人的画面都算得出来
        self.assertEqual(t.prompts()[1]['title'], '这一局没有情侣')
        self.assertEqual(t.prompts()[5]['title'], '你没有被选为情侣')
        t.night(kill=0)
        self.assertEqual(t.g['lovers'], [])
        self.assertEqual(t.room.phase, 'day')

    def test_lovers_die_together_in_the_day(self):
        t = Table(self.D)
        t.deal()
        t.night(lovers=(5, 6), kill=0)
        t.exile(5)
        self.assertEqual(t.alive(), [1, 2, 3, 4, 7, 8, 9, 10, 11, 12])
        self.assertEqual(t.g['seats'][6]['cause'], 'love')

    def test_wolf_and_good_lovers_are_third_party(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'cupid'])
        t.deal()
        t.night(lovers=(1, 3), kill=0)
        self.assertTrue(t.g['third'])
        self.assertIn('第三方', t.view(1)['me']['notes'][0])
        self.assertIn('第三方', t.view(7)['me']['notes'][0])
        t.exile(2)                                           # 另一只狼出局：狼还剩情侣狼，没结束
        self.assertEqual(t.room.phase, 'day')
        t.night(kill=4)
        t.exile(5)
        t.night(kill=6)                                      # 剩 1、3（情侣）和 7（丘比特）
        self.assertEqual(t.view(1)['over']['winner'], 'third')

    def test_third_party_dead_then_normal_rules(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'cupid'])
        t.deal()
        t.night(lovers=(1, 3), kill=0)
        t.exile(1)                                           # 情侣双双出局
        self.assertEqual(t.alive(), [2, 4, 5, 6, 7])
        t.confirm_dead()
        t.night(kill=6)                                      # 丘比特已是第三方，不算好人的神
        self.assertEqual(t.view(2)['over']['winner'], 'wolf')


class Mixed(unittest.TestCase):
    """混血儿：第一夜选榜样，和榜样同输同赢；被查验算好人；不影响游戏什么时候结束。"""
    # 1-3 狼，4-7 民，8 预言家，9 女巫，10 猎人，11 骑士，12 混血儿
    D = ['wolf'] * 3 + ['villager'] * 4 + ['seer', 'witch', 'hunter', 'knight', 'mixed']

    def test_wakes_first_only_on_the_first_night_and_must_pick_someone_else(self):
        t = Table(self.D)
        t.deal()
        self.assertEqual(t.view(12)['me']['notes'], [])
        t.heard = []
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {12: 'mixed'})           # 最先睁眼，别人的手机上什么都没有
        pr = t.prompts()[12]
        self.assertEqual(pr['targets'], list(range(1, 12)))  # 不能选自己
        self.assertIsNone(pr['skip'])                        # 必须选
        with self.assertRaises(GameError):
            t.act(12, 'night', targets=[12])
        with self.assertRaises(GameError):
            t.act(12, 'night', skip=True)
        with self.assertRaises(GameError):
            t.act(5, 'night', targets=[2])                   # 不是混血儿
        t.act(12, 'night', targets=[2])
        t.flush()
        self.assertEqual(t.g['model'], 2)
        self.assertIn('你的榜样是 2号', t.view(12)['me']['notes'])
        t.night(kill=0)
        self.assertEqual(t.heard[:5], ['night_fall', 'mixed_open', 'mixed_prompt', 'mixed_close', 'wolf_open'])
        t.no_exile()
        t.heard = []
        t.night(kill=0)
        self.assertNotIn('mixed_open', t.heard)              # 只有第一夜
        self.assertEqual(t.g['model'], 2)

    def test_nobody_else_learns_anything(self):
        t = Table(self.D)
        t.deal()
        t.night(model=2, kill=0)
        self.assertEqual([m['seat'] for m in t.view(1)['me']['mates']], [2, 3])   # 跟了狼也不和狼见面
        for s in range(1, 12):
            self.assertNotIn('榜样', repr(t.view(s)))        # 榜样本人和其他人都不知道
            self.assertNotIn("'model'", repr(t.view(s)))
        v = t.view(12)
        self.assertNotIn('mates', v['me'])
        self.assertNotIn('狼人', repr(v['me']['notes']))     # 混血儿自己也不知道榜样是什么身份
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {1: 'wolf', 2: 'wolf', 3: 'wolf'})   # 第二夜：没有混血儿环节，他也不在狼队里
        self.assertEqual(t.prompts()[1]['wolves'], [1, 2, 3])

    def test_follows_a_wolf_checks_as_good_and_loses_when_the_wolves_are_out(self):
        t = Table(self.D)
        t.deal()
        t.night(model=2, kill=0, check=12)
        self.assertIn('第1夜查验 12号：好人', t.view(8)['me']['notes'])   # 预言家验混血儿永远是好人
        self.assertEqual(t.room._camp(12), 'wolf')
        t.exile(1)
        t.night(kill=0)
        t.exile(2)                                           # 榜样出局，混血儿还是狼人阵营
        self.assertEqual(t.room._camp(12), 'wolf')
        t.night(kill=0)
        t.exile(3)
        self.assertEqual(t.room.phase, 'over')               # 狼人全部出局就结束，不用等跟狼的混血儿
        o = t.view(12)['over']
        self.assertEqual(o['winner'], 'good')
        self.assertEqual(o['camps'][12], 'wolf')             # 他跟着狼人输了
        self.assertEqual(o['model'], 2)
        self.assertTrue(t.g['seats'][12]['alive'])
        self.assertIn('混血儿 12号 的榜样是 2号，属于狼人阵营', o['log'])

    def test_wolves_win_by_killing_the_villagers_without_touching_him(self):
        for model, camp in ((5, 'good'), (1, 'wolf')):
            t = Table(['wolf', 'wolf', 'villager', 'villager', 'seer', 'witch', 'mixed'])
            t.deal()
            t.night(model=model, kill=3)
            t.no_exile()
            t.night(kill=4)                                  # 两个村民都死了：屠民，混血儿不算民
            o = t.view(7)['over']
            self.assertEqual(o['winner'], 'wolf')
            self.assertEqual(o['camps'][7], camp)
            self.assertTrue(t.g['seats'][7]['alive'])

    def test_does_not_count_as_a_god_either(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'mixed'])
        t.deal()
        t.night(model=3, kill=6)                             # 唯一的神死了：屠神
        self.assertEqual(t.view(1)['over']['winner'], 'wolf')

    def test_game_goes_on_while_the_others_are_alive(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'seer', 'witch', 'mixed'])
        t.deal()
        t.night(model=1, kill=0)
        t.exile(7)                                           # 混血儿出局不影响任何一边
        self.assertEqual(t.room.phase, 'day')
        t.night(kill=3)
        self.assertEqual(t.room.phase, 'day')

    def test_host_skipping_him_leaves_him_on_the_good_side(self):
        t = Table(['mixed'] + self.D[:11])                   # 房主就是混血儿
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {1: 'mixed'})
        t.act(1, 'skip')
        t.flush()
        self.assertEqual(t.g['model'], 0)
        self.assertIn('第一夜没有选榜样，你算好人阵营', t.view(1)['me']['notes'])
        self.assertEqual(t.room._camp(1), 'good')
        t.night(kill=0)
        self.assertEqual(t.room.phase, 'day')
        for w in (2, 3, 4):
            t.exile(w)
            if w != 4:
                t.night(kill=0)
        o = t.view(1)['over']
        self.assertEqual(o['winner'], 'good')
        self.assertEqual(o['model'], 0)
        self.assertEqual(o['camps'][1], 'good')
        self.assertIn('混血儿 1号 没有选榜样，属于好人阵营', o['log'])

    def test_third_party_that_wins_at_the_link_wins_at_dawn(self):
        """1 狼，2 村民，3 丘比特，4 混血儿：丘比特连 1 和 2 以后，除了混血儿全是第三方，夜里没人死也算赢。"""
        for kill in (0, 2, 1, 3):
            t = Table(['wolf', 'villager', 'cupid', 'mixed'], sheriff=True)
            t.deal()
            t.night(model=3, lovers=(1, 2), kill=kill)
            o = t.view(1)['over']
            self.assertEqual(o['winner'], 'third', kill)     # 先满足胜利条件的一方获胜，不看之后谁先死
            self.assertEqual(o['camps'][4], 'third')         # 他跟的是丘比特
            self.assertEqual(t.heard[-1], 'win_third')

    def test_in_win_all_mode_he_still_does_not_count(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'seer', 'witch', 'mixed'], win='all')
        t.deal()
        t.night(model=3, kill=3)
        t.exile(4)
        t.night(kill=5)
        self.assertEqual(t.room.phase, 'day')                # 屠城：女巫还活着
        t.exile(6)
        o = t.view(7)['over']
        self.assertEqual(o['winner'], 'wolf')               # 神和民都死光就结束，跟好人的混血儿活着也一样
        self.assertEqual(o['camps'][7], 'good')
        self.assertTrue(t.g['seats'][7]['alive'])

    def test_a_board_without_gods_only_ends_on_the_villagers(self):
        t = Table(['wolf', 'wolf', 'villager', 'villager', 'villager', 'mixed'])
        t.deal()
        t.night(model=1, kill=3)
        self.assertEqual(t.room.phase, 'day')                # 他不算神：没有神的板子不会因此结束
        t.no_exile()
        t.night(kill=4)
        self.assertEqual(t.room.phase, 'day')
        t.no_exile()
        t.night(kill=5)
        self.assertEqual(t.view(6)['over']['winner'], 'wolf')

    def test_never_holds_the_knife(self):
        # 1 狼，2 石像鬼，3-5 民，6 预言家，7 女巫，8 混血儿
        t = Table(['wolf', 'gargoyle', 'villager', 'villager', 'villager', 'seer', 'witch', 'mixed'])
        t.deal()
        t.night(model=1, kill=0)
        self.assertEqual(t.room._camp(8), 'wolf')
        t.exile(1)                                           # 狼群死光：轮到石像鬼刀人，跟狼的混血儿没有刀
        t.confirm_dead()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {2: 'wolf'})

    def test_model_can_be_the_mech_wolf_or_the_gargoyle(self):
        for special in ('mech', 'gargoyle'):
            # 1-2 狼，3 特殊狼，4-6 民，7 预言家，8 女巫，9 混血儿
            t = Table(['wolf', 'wolf', special, 'villager', 'villager', 'villager', 'seer', 'witch', 'mixed'])
            t.deal()
            t.night(model=3, kill=0)
            self.assertEqual(t.room._camp(9), 'wolf', special)

    def test_host_drops_during_his_own_step(self):
        deck = ['mixed'] + ['wolf'] * 3 + ['villager'] * 4 + ['seer', 'witch', 'hunter', 'guard']
        t = Table(deck)                                      # 房主就是混血儿
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {1: 'mixed'})
        t.drop(1)                                            # 他的手机没电了
        t.act(5, 'take_host')                                # 5 号接手播报
        with self.assertRaises(GameError):
            t.act(5, 'night', targets=[2])                   # 别人替不了他
        mine = t.room.request_claim(1, '房主')               # 借一台手机回来认领自己的座位
        t.act(5, 'claim_ok', rid=mine)
        t.room.attach(t.pid[1])
        self.assertEqual(t.prompts()[1]['type'], 'mixed')   # 新手机上接着选
        t.act(1, 'night', targets=[2])
        self.assertEqual(t.g['model'], 2)

        t = Table(deck)
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.drop(1)
        t.act(5, 'take_host')
        t.act(5, 'skip', key=t.view(5)['skip_key'])          # 等不回来：接手播报的人跳过这个环节
        self.assertEqual(t.g['model'], 0)
        self.assertEqual(t.room._camp(1), 'good')

    def test_checks_duels_and_hunts_treat_him_as_good(self):
        # 1-3 狼，4-6 民，7 通灵师，8 女巫，9 守墓人，10 骑士，11 混血儿
        t = Table(['wolf'] * 3 + ['villager'] * 3 + ['psychic', 'witch', 'gravekeeper', 'knight', 'mixed'])
        t.deal()
        t.night(model=1, kill=0, psy=11)
        self.assertIn('第1夜查验 11号：混血儿', t.view(7)['me']['notes'])
        t.act(10, 'duel', target=11)                         # 决斗跟狼的混血儿：他不是狼人，骑士出局
        t.flush()
        self.assertFalse(t.g['seats'][10]['alive'])
        self.assertTrue(t.g['seats'][11]['alive'])
        t.exile(11)
        t.night(kill=0)
        self.assertIn('第1天被放逐的 11号：好人', t.view(9)['me']['notes'])

        # 1-3 狼，4-6 民，7 预言家，8 女巫，9 白痴，10 猎魔人，11 混血儿
        t = Table(['wolf'] * 3 + ['villager'] * 3 + ['seer', 'witch', 'idiot', 'witcher', 'mixed'])
        t.deal()
        t.night(model=1, kill=0)
        t.no_exile()
        t.night(kill=0, hunt=11)                             # 狩猎跟狼的混血儿：猎魔人自己出局
        self.assertEqual(t.day()['night_deaths'], [10])
        self.assertTrue(t.g['seats'][11]['alive'])

    def test_mech_wolf_learning_him_gets_nothing(self):
        # 1-3 狼，4 机械狼，5-7 民，8 混血儿，9 通灵师，10 女巫，11 猎人，12 守卫
        t = Table(['wolf'] * 3 + ['mech'] + ['villager'] * 3 + ['mixed', 'psychic', 'witch', 'hunter', 'guard'])
        t.deal()
        t.night(model=5, kill=0, mech=8, psy=4)
        self.assertIn('第1夜学习 8号：混血儿', t.view(4)['me']['notes'])
        self.assertIn('第1夜查验 4号：混血儿', t.view(9)['me']['notes'])   # 学了以后被查验显示成混血儿
        self.assertFalse(t.g['mech']['double'])
        self.assertFalse(t.g['mech']['poison'])
        t.no_exile()
        t.act(1, 'start_night')
        t.flush()
        self.assertIsNone(t.room._mech_skill())             # 第二夜起也没有能用的技能

    def test_as_a_lover_he_is_a_good_card_and_learns_nothing_about_his_model(self):
        # 1 混血儿，2-3 狼，4-6 民，7 预言家，8 丘比特
        D = ['mixed', 'wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'cupid']
        seen = {}
        for model in (3, 4):                                 # 榜样是狼 / 是好人
            for pair, third in (((1, 2), True), ((1, 5), False)):
                t = Table(D)
                t.deal()
                t.act(1, 'start_night')
                t.flush()
                self.assertEqual(t.types(), {1: 'mixed'})    # 混血儿在丘比特之前
                t.act(1, 'night', targets=[model])
                t.flush()
                self.assertEqual(t.types(), {8: 'cupid'})
                t.act(8, 'night', targets=list(pair))
                t.flush()
                self.assertEqual(t.g['third'], third)        # 和狼连是人狼恋，和好人连是好人情侣，不看榜样
                self.assertEqual(t.room._camp(1), 'third' if third else 'good')
                self.assertEqual(t.room._camp(8), 'third' if third else 'good')
                lines = t.prompts()[1]['lines']
                self.assertIn('不再跟随榜样', lines[-1])
                notes = t.view(1)['me']['notes']
                self.assertTrue(any('不再跟随榜样' in n for n in notes))
                text = repr((lines, notes)).replace('你的榜样是 %d号' % model, '你的榜样是 N号')
                seen.setdefault(pair, set()).add(text)
        for pair, texts in seen.items():
            self.assertEqual(len(texts), 1, texts)          # 榜样是狼还是好人，他看到的一模一样

    def test_a_couple_with_him_always_has_a_wolf_card_to_kill_at_night(self):
        """跟了狼的混血儿和好人连成情侣：不算人狼恋。狼牌全部出局就是好人赢，不会僵住。"""
        # 1 混血儿，2 狼，3 民，4 白痴，5 丘比特，6 预言家，7 民
        t = Table(['mixed', 'wolf', 'villager', 'idiot', 'cupid', 'seer', 'villager'])
        t.deal()
        t.night(model=2, lovers=(1, 3), kill=6)
        self.assertFalse(t.g['third'])
        t.exile(4)                                           # 白痴翻牌
        t.night(kill=7)
        t.exile(2)                                           # 最后一张狼牌
        o = t.view(1)['over']
        self.assertEqual(o['winner'], 'good')
        self.assertEqual(o['camps'][1], 'good')              # 情侣按情侣算：他跟着好人赢
        self.assertIn('混血儿 1号 被连成情侣，属于好人阵营', o['log'])

    def test_following_the_third_party_wins_with_them(self):
        # 1-2 狼，3-5 民，6 预言家，7 丘比特，8 混血儿；1 和 3 是人狼恋
        D = ['wolf', 'wolf', 'villager', 'villager', 'villager', 'seer', 'cupid', 'mixed']
        for model, camp in ((7, 'third'), (4, 'good')):
            t = Table(D)
            t.deal()
            t.night(model=model, lovers=(1, 3), kill=0)
            self.assertEqual(t.room._camp(8), camp)
            t.exile(2)
            t.night(kill=4 if model != 4 else 5)
            t.exile(5 if model != 4 else 6)
            if model == 4:                                   # 榜样 4 号还活着：先把他放逐
                t.night(kill=0)
                t.exile(4)
            else:
                t.night(kill=6)
            o = t.view(8)['over']                            # 只剩情侣、丘比特和混血儿
            self.assertEqual(o['winner'], 'third')           # 混血儿活着也挡不住第三方获胜
            self.assertEqual(o['camps'][8] == 'third', camp == 'third')
            self.assertTrue(t.g['seats'][8]['alive'])


class Assets(unittest.TestCase):
    """加了新角色以后，头像、台词、语音文件一样都不能少。"""

    def test_every_role_has_a_portrait(self):
        for r in ROLE_ORDER:
            self.assertTrue(os.path.exists(os.path.join(ROOT, 'public', 'avatars', r + '.svg')), r)

    def test_mixed_counts_as_neither_god_nor_villager(self):
        from roles import GODS
        self.assertEqual(ROLES['mixed']['kind'], 'none')
        self.assertNotIn('mixed', GODS)
        self.assertEqual(ROLES['mixed']['team'], 'good')     # 被查验是好人

    def test_client_test_role_table_matches_roles_py(self):
        import re
        with open(os.path.join(ROOT, 'tests', 'client_sim.js'), encoding='utf-8') as f:
            js = f.read()
        rows = re.findall(r"\{ id: '(\w+)', name: '([^']+)', team: '(\w+)', kind: '(\w+)'", js)
        self.assertTrue(rows)
        for rid, name, team, kind in rows:
            self.assertEqual((name, team, kind), (ROLES[rid]['name'], ROLES[rid]['team'], ROLES[rid]['kind']), rid)

    def test_every_character_players_see_is_in_the_font(self):
        """界面字体只是子集：角色、台词、板子名里出现了新字，要重新运行 tools/fonts/fetch.py。"""
        import re
        with open(os.path.join(ROOT, 'public', 'fonts', 'fonts.css'), encoding='utf-8') as f:
            css = f.read()
        have = set()
        for rng in re.findall(r'unicode-range:\s*([^;}]+)', css):
            for part in rng.split(','):
                a, _, b = part.strip()[2:].partition('-')
                have.update(chr(c) for c in range(int(a, 16), int(b or a, 16) + 1))
        text = (''.join(r['name'] + r['desc'] for r in ROLES.values()) + ''.join(CLIPS.values())
                + ''.join(p['name'] for p in PRESETS))
        missing = sorted(set(c for c in text if '\u4e00' <= c <= '\u9fff') - have - set('回'))   # 「回」故意不放进子集
        self.assertEqual(missing, [], '字体子集里没有这些字，请运行 python3 tools/fonts/fetch.py')

    def test_every_night_step_has_its_lines_and_audio(self):
        import json
        with open(os.path.join(ROOT, 'public', 'audio', 'manifest.json'), encoding='utf-8') as f:
            manifest = json.load(f)
        for step, _need, _when in NIGHT_STEPS:
            for x in ('_open', '_prompt', '_close'):
                self.assertIn(step + x, CLIPS)
        for cid in CLIPS:
            self.assertTrue(os.path.exists(os.path.join(ROOT, 'public', 'audio', cid + '.m4a')), cid)
            self.assertIn(cid, manifest)


class Sheriff(unittest.TestCase):
    def start(self, deck=D9, **night):
        t = Table(deck, sheriff=True)
        t.deal()
        t.heard = []
        t.night(**night)
        return t

    def test_election_happens_before_deaths_are_announced(self):
        t = self.start(kill=4)
        self.assertEqual(t.stage(), 'e_signup')
        self.assertNotIn('died_last_night', t.heard)
        self.assertTrue(all(s['alive'] for s in t.view(5)['seats']))   # 还没人知道 4 号倒牌
        self.assertEqual(t.day(4)['elect']['mine'], 'signup')          # 倒牌的人照常参加
        for s in range(1, 10):
            # 举手是同时的：没选完之前看不到别人选了什么
            self.assertEqual(t.day(9)['elect']['all'], [])
            t.act(s, 'elect_run', run=s in (2, 4, 7))
        t.flush()
        e = t.day()['elect']
        self.assertEqual((t.stage(), e['all']), ('e_speech', [2, 4, 7]))
        self.assertEqual(sorted(e['order']), [2, 4, 7])
        with self.assertRaises(GameError):
            t.act(2, 'elect_next')                           # 只有房主能推进
        t.act(1, 'elect_next')                               # 房主：进入退水环节
        self.assertEqual(t.stage(), 'e_withdraw')
        self.assertEqual(t.day(2)['elect']['mine'], 'withdraw')
        self.assertIsNone(t.day(5)['elect']['mine'])
        t.act(2, 'elect_withdraw', out=True)
        self.assertEqual(t.day(5)['elect']['withdrawn'], [])   # 也是同时亮
        t.act(4, 'elect_withdraw', out=False)
        t.act(7, 'elect_withdraw', out=False)
        t.flush()
        e = t.day()['elect']
        self.assertEqual((t.stage(), e['cands'], e['withdrawn']), ('e_vote', [4, 7], [2]))
        self.assertEqual(e['vote']['voters'], [1, 3, 5, 6, 8, 9])      # 只有警下投票
        with self.assertRaises(GameError):
            t.act(2, 'elect_vote', target=7)                 # 退水的人不能投
        with self.assertRaises(GameError):
            t.act(4, 'elect_vote', target=4)                 # 警上的人不能投
        with self.assertRaises(GameError):
            t.act(1, 'elect_vote', target=2)                 # 不能投已经退水的
        for s in (1, 3, 5, 6):
            t.act(s, 'elect_vote', target=4)
        for s in (8, 9):
            t.act(s, 'elect_vote', target=7)
        self.assertNotIn('died_last_night', t.heard)
        t.flush()
        self.assertEqual(t.g['sheriff'], 4)
        self.assertIn('elect_win', t.heard)
        self.assertLess(t.heard.index('elect_win'), t.heard.index('died_last_night'))
        # 当选的 4 号其实昨夜倒牌了：公布死讯后要决定警徽去向
        self.assertEqual(t.day()['night_deaths'], [4])
        self.assertTrue(t.day(4)['settle']['mine']['badge'])
        with self.assertRaises(GameError):
            t.act(4, 'settle', target=0)                     # 必须先决定警徽
        t.act(4, 'settle', target=0, badge=7)
        t.flush()
        self.assertEqual(t.g['sheriff'], 7)
        self.assertTrue(t.view(1)['seats'][6]['sheriff'])
        self.assertIn('badge_pass', t.heard)

    def test_nobody_runs(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=False)
        t.flush()
        self.assertEqual((t.g['badge'], t.g['sheriff']), ('lost', 0))
        self.assertEqual(t.stage(), 'discuss')
        self.assertIn('elect_lost', t.heard)

    def test_single_candidate_after_withdraw_wins(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s in (2, 7))
        t.flush()
        t.act(1, 'elect_next')
        t.act(2, 'elect_withdraw', out=True)
        t.act(7, 'elect_withdraw', out=False)
        t.flush()
        self.assertEqual(t.g['sheriff'], 7)

    def test_everyone_runs_and_nobody_withdraws(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=True)
        t.flush()
        t.act(1, 'elect_next')
        for s in range(1, 10):
            t.act(s, 'elect_withdraw', out=False)
        t.flush()
        self.assertEqual(t.g['badge'], 'lost')               # 没有警下，没人能投票

    def test_withdrawn_players_vote_in_the_pk_round(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s in (2, 4, 7, 9))
        t.flush()
        t.act(1, 'elect_next')
        for s in (2, 4, 7, 9):
            t.act(s, 'elect_withdraw', out=s == 9)
        t.flush()
        v = t.day()['elect']['vote']
        self.assertEqual(v['voters'], [1, 3, 5, 6, 8])       # 第一轮：退水的 9 号不投
        for s, to in ((1, 2), (3, 2), (5, 4), (6, 4), (8, 7)):
            t.act(s, 'elect_vote', target=to)
        t.flush()
        self.assertEqual((t.stage(), t.day()['elect']['pk']), ('e_pk', [2, 4]))
        t.heard = []
        t.act(1, 'elect_next')
        v = t.day()['elect']['vote']
        self.assertEqual((v['round'], v['voters']), (2, [1, 3, 5, 6, 8, 9]))   # PK：警下 + 退水
        self.assertEqual(t.day(9)['elect']['mine'], 'vote')
        self.assertIsNone(t.day(7)['elect']['mine'])         # 留在警上没进 PK 的 7 号不投
        with self.assertRaises(GameError):
            t.act(7, 'elect_vote', target=2)
        for s, to in ((1, 2), (3, 2), (5, 4), (6, 4), (8, 0), (9, 4)):
            t.act(s, 'elect_vote', target=to)
        t.flush()
        self.assertIn('elect_vote_pk', t.heard)
        self.assertEqual(t.g['sheriff'], 4)                  # 退水的 9 号那一票打破了平局

    def test_tie_pk_then_tie_again(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s in (2, 4, 7))
        t.flush()
        t.act(1, 'elect_next')
        for s in (2, 4, 7):
            t.act(s, 'elect_withdraw', out=False)
        t.flush()
        for s, to in ((1, 2), (3, 2), (5, 4), (6, 4), (8, 7), (9, 0)):
            t.act(s, 'elect_vote', target=to)
        t.flush()
        e = t.day()['elect']
        self.assertEqual((t.stage(), e['pk']), ('e_pk', [2, 4]))
        t.act(1, 'elect_next')                               # PK 发言结束，再投
        v = t.day()['elect']['vote']
        self.assertEqual((v['round'], v['cands'], v['voters']), (2, [2, 4], [1, 3, 5, 6, 8, 9]))
        with self.assertRaises(GameError):
            t.act(7, 'elect_vote', target=2)                 # 落选的警上玩家也不能投
        for s, to in ((1, 2), (3, 2), (5, 4), (6, 4), (8, 0), (9, 0)):
            t.act(s, 'elect_vote', target=to)
        t.flush()
        self.assertEqual(t.g['badge'], 'lost')               # 再次平票，警徽流失
        self.assertEqual(t.stage(), 'discuss')

    def test_sheriff_vote_counts_one_and_a_half(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s == 7)
        t.flush()
        t.act(1, 'elect_next')
        t.act(7, 'elect_withdraw', out=False)
        t.flush()
        self.assertEqual(t.g['sheriff'], 7)
        t.act(1, 'start_vote')
        for s, to in ((1, 5), (2, 5), (3, 5), (4, 1), (5, 1), (7, 1), (6, 0), (8, 0), (9, 0)):
            t.act(s, 'vote', target=to)
        t.flush()
        res = t.day()['results'][0]
        self.assertEqual(res['counts'], {5: 3, 1: 3.5})      # 3 票 对 2 + 1.5 票
        self.assertFalse(t.g['seats'][1]['alive'])

    def test_sheriff_chooses_speaking_order(self):
        t = self.start(kill=8)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s == 7)
        t.flush()
        t.act(1, 'elect_next')
        t.act(7, 'elect_withdraw', out=False)
        t.flush()
        t.confirm_dead()
        d = t.day(7)
        self.assertEqual(d['stage'], 'discuss')
        self.assertIsNone(d['speak'])
        self.assertTrue(d['order']['mine'])
        self.assertFalse(t.day(2)['order']['mine'])
        # 8 号倒牌了：往上数从 9 号开始，往下数从 6 号开始，警长自己最后发言
        self.assertEqual(d['order']['opts'], [{'start': 9, 'dir': 1}, {'start': 6, 'dir': -1}])
        with self.assertRaises(GameError):
            t.act(2, 'order', i=0)
        t.act(7, 'order', i=1)
        self.assertEqual(t.day()['speak'], {'start': 6, 'dir': -1})

    def test_boom_during_election_postpones_then_loses_badge(self):
        t = self.start(kill=4)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s in (2, 7))
        t.flush()
        t.act(2, 'boom')                                     # 警上自爆
        t.flush()
        self.assertEqual((t.g['badge'], t.g['elect_day']), ('open', 2))
        self.assertIn('elect_postponed', t.heard)
        self.assertEqual(t.day()['night_deaths'], [4])       # 自爆后照常公布昨夜死讯
        t.confirm_dead()
        self.assertEqual(t.room.phase, 'night')              # 然后直接天黑
        t.heard = []
        t.night(kill=5)
        self.assertEqual(t.stage(), 'e_signup')              # 第二天重新竞选
        self.assertEqual(t.day()['elect']['players'], [1, 3, 5, 6, 7, 8, 9])
        for s in t.day()['elect']['players']:
            t.act(s, 'elect_run', run=s in (3, 7))
        t.flush()
        t.act(3, 'boom')                                     # 再爆：警徽流失
        t.flush()
        self.assertEqual(t.g['badge'], 'lost')
        t.confirm_dead()
        t.night(kill=0)
        self.assertEqual(t.stage(), 'discuss')               # 之后不再竞选

    def test_sheriff_can_tear_the_badge(self):
        t = self.start(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s == 7)
        t.flush()
        t.act(1, 'elect_next')
        t.act(7, 'elect_withdraw', out=False)
        t.flush()
        t.exile(7)
        self.assertTrue(t.day(7)['settle']['mine']['badge'])
        t.act(7, 'settle', target=0, badge=0)
        t.flush()
        self.assertEqual((t.g['sheriff'], t.g['badge']), (0, 'lost'))
        self.assertIn('badge_tear', t.heard)

    def test_host_can_force_election_forward(self):
        t = self.start(kill=0)
        t.act(3, 'elect_run', run=True)
        t.act(5, 'elect_run', run=True)
        with self.assertRaises(GameError):
            t.act(2, 'elect_close')
        t.act(1, 'elect_close')                              # 没表态的算不上警
        t.flush()
        self.assertEqual(t.day()['elect']['all'], [3, 5])
        t.act(1, 'elect_next')
        t.act(1, 'elect_close')                              # 没表态的算不退水
        t.flush()
        self.assertEqual(t.stage(), 'e_vote')
        t.act(1, 'elect_vote', target=3)
        t.act(1, 'elect_close')                              # 没投的算弃票
        t.flush()
        self.assertEqual(t.g['sheriff'], 3)

    def test_no_election_when_switched_off(self):
        t = Table(D9, sheriff=False)
        t.deal()
        t.night(kill=0)
        self.assertEqual(t.stage(), 'discuss')
        self.assertEqual(t.g['badge'], 'off')


class HiddenInformation(unittest.TestCase):
    """任何人都不能从自己手机收到的数据里看到别人的底牌。"""

    def test_views_do_not_leak(self):
        t = Table(D12)
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', targets=[9])
        t.flush()
        for w in (1, 2, 3, 4):
            t.act(w, 'wolf_pick', target=5)
        for s in range(1, 13):
            v = t.view(s)
            self.assertTrue(all(x['shown'] is None for x in v['seats']))
            self.assertNotIn('over', v)
            text = repr(v)
            if s not in (1, 2, 3, 4):
                self.assertNotIn('mates', v['me'])
                self.assertIsNone(v['night']['prompt'])      # 好人看不到狼在选谁
                self.assertNotIn('picks', text)
            if s != 10:
                self.assertNotIn('解药', text)
        self.assertEqual([m['seat'] for m in t.view(2)['me']['mates']], [1, 3, 4])

    def test_death_cause_hidden_until_game_over(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4, poison=5)
        for s in range(1, 10):
            self.assertNotIn('poison', repr(t.view(s)).replace("'poison': False", ''))
            self.assertNotIn('被毒', repr(t.view(s)))

    def test_notes_are_private(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4, check=2)
        self.assertIn('第1夜查验 2号：狼人', t.view(7)['me']['notes'])
        for s in (1, 2, 3, 4, 5, 6, 8, 9):
            self.assertNotIn('查验', repr(t.view(s)))


class Lobby(unittest.TestCase):
    def test_everyone_can_see_who_has_looked_at_their_card(self):
        t = Table(D9)
        t.act(1, 'deal')
        t.act(2, 'seen')
        t.act(7, 'seen')
        for s in (1, 2, 5):
            self.assertEqual(t.view(s)['deal']['ready'], [2, 7])
        self.assertEqual((t.view(2)['deal']['seen'], t.view(5)['deal']['seen']), (True, False))

    def test_settle_shows_who_has_confirmed(self):
        t = Table(D9)
        t.deal()
        t.night(kill=4, poison=6)
        st = t.day()['settle']
        self.assertEqual((st['waiting'], st['done']), ([4, 6], []))
        t.act(4, 'settle', target=0)
        st = t.day()['settle']
        self.assertEqual((st['waiting'], st['done']), ([6], [4]))

    def test_deal_needs_everyone_seated(self):
        t = Table(D9)
        t.act(5, 'stand')
        with self.assertRaises(GameError):
            t.act(1, 'deal')
        with self.assertRaises(GameError):
            t.act(5, 'sit', seat=4)                          # 有人了
        t.act(5, 'sit', seat=5)
        with self.assertRaises(GameError):
            t.act(2, 'deal')                                 # 不是房主
        t.act(1, 'deal')
        self.assertEqual(t.room.phase, 'deal')
        self.assertEqual(sorted(t.g['seats'][s]['role'] for s in range(1, 10)), sorted(D9))

    def test_shrinking_board_unseats_extra_players(self):
        t = Table(D9)
        t.act(1, 'config', roles=full_roles(PRESETS[0]['roles']))  # 改成 6 人
        self.assertEqual(t.room.n, 6)
        self.assertEqual(t.view(7)['you']['seat'], 0)
        self.assertEqual(len(t.view(1)['seats']), 6)

    def test_bad_boards_rejected(self):
        t = Table(D9)
        t.act(1, 'config', roles={'wolf': 5, 'villager': 4})
        self.assertIsNotNone(t.view(1)['err'])
        with self.assertRaises(GameError):
            t.act(1, 'deal')
        t.act(1, 'config', roles={'seer': 3, 'wolf': 1, 'villager': 3})
        self.assertEqual(t.room.config['roles']['seer'], 1)   # 神职最多一张

    def test_every_preset_is_a_valid_board(self):
        for p in PRESETS:
            cfg = dict(game.default_config(), roles=full_roles(p['roles']))
            self.assertIsNone(game.validate_config(cfg), p['name'])
            self.assertEqual(sum(p['roles'].values()), int(p['name'].split('人')[0]), p['name'])
            self.assertTrue(all(r in ROLES for r in p['roles']))

    def test_claim_seat_after_losing_phone(self):
        t = Table(D9)
        t.deal()
        with self.assertRaises(GameError):
            t.room.request_claim(5, '新手机')                # 还在线，不能抢
        t.drop(5)
        self.assertEqual([x['seat'] for x in t.room.offline_seats()], [5])
        old_token = t.room.players[t.pid[5]]['token']
        rid = t.room.request_claim(5, '新手机')
        t.act(1, 'claim_ok', rid=rid)
        state, p = t.room.claim_status(rid)
        self.assertEqual((state, p['id'], p['name']), ('ok', t.pid[5], '新手机'))
        self.assertNotEqual(p['token'], old_token)
        self.assertIsNone(t.room.auth(p['id'], old_token))

    def test_host_takeover_only_when_host_offline(self):
        t = Table(D9)
        with self.assertRaises(GameError):
            t.act(2, 'take_host')
        t.drop(1)
        t.act(2, 'take_host')
        self.assertTrue(t.view(2)['you']['host'])


class Connections(unittest.TestCase):
    """掉线判定：手机锁屏、切后台、换网络都会让连接断一下，不能因此打断游戏。"""

    def online(self, t, seat, viewer=2):
        return t.view(viewer)['seats'][seat - 1]['online']

    def test_a_quick_reconnect_never_shows_as_offline(self):
        t = Table(D9)
        now = time.time()
        t.room.detach(t.pid[5], now=now)
        t.room.sweep(now=now + game.OFFLINE_GRACE - 1)
        self.assertTrue(self.online(t, 5))               # 还在宽限期里
        t.room.attach(t.pid[5], now=now + 3)
        t.room.sweep(now=now + 600)
        self.assertTrue(self.online(t, 5))               # 连回来了，之后一直在线

    def test_offline_only_after_the_grace_period(self):
        t = Table(D9)
        now = time.time()
        t.room.detach(t.pid[5], now=now)
        t.room.sweep(now=now + game.OFFLINE_GRACE + 1)
        self.assertFalse(self.online(t, 5))
        t.room.attach(t.pid[5], now=now + 30)
        self.assertTrue(self.online(t, 5))

    def test_a_flapping_player_does_not_block_dealing_but_a_gone_one_does(self):
        t = Table(D9)
        now = time.time()
        t.room.detach(t.pid[5], now=now)
        t.room.sweep(now=now + 2)
        t.room.attach(t.pid[5], now=now + 3)
        t.room.detach(t.pid[6], now=now)
        t.room.sweep(now=now + 60)
        with self.assertRaises(GameError):
            t.act(1, 'deal')                             # 6 号真的走了
        t.room.attach(t.pid[6], now=now + 61)
        t.act(1, 'deal')

    def test_a_frozen_phone_goes_offline_when_it_stops_answering_heartbeats(self):
        t = Table(D9)
        now = time.time()
        t.room.detach(t.pid[5], now=now)
        t.room.attach(t.pid[5], hb=True, now=now)        # 换成新版页面：会回应心跳
        t.room.sweep(now=now + game.ALIVE_FOR - 1)
        self.assertTrue(self.online(t, 5))
        t.room.sweep(now=now + game.ALIVE_FOR + 1)
        self.assertFalse(self.online(t, 5))              # 连接还在，但页面已经不动了
        t.room.touch(t.pid[5], now=now + 40)             # 手机醒过来，回应了一次
        self.assertTrue(self.online(t, 5))
        t.room.sweep(now=now + 600)                      # 4 号的页面不回应心跳（老版本 / 脚本），只看连接
        self.assertTrue(self.online(t, 4))

    def test_heartbeat_silence_only_counts_when_every_connection_answers_heartbeats(self):
        t = Table(D9)                                    # 5 号已经有一条不回应心跳的老连接
        now = time.time()
        t.room.attach(t.pid[5], hb=True, now=now)        # 又开了一个新版页面……
        t.room.detach(t.pid[5], hb=True, now=now + 1)    # ……然后关掉了。剩下的还是那条老连接
        t.room.sweep(now=now + 600)
        self.assertTrue(self.online(t, 5))               # 不能因为它不回应心跳就判它掉线
        t.room.attach(t.pid[6], hb=True, now=now)        # 6 号：一条老连接 + 一条新连接同时在
        t.room.sweep(now=now + 600)
        self.assertTrue(self.online(t, 6))
        t.room.detach(t.pid[6], now=now + 601)           # 老连接断了，只剩会回应心跳的那条，而它一直没回应
        t.room.sweep(now=now + 700)
        self.assertFalse(self.online(t, 6))

    def test_a_phone_that_can_only_poll_stays_online_while_it_polls(self):
        t = Table(D9)
        now = time.time()
        t.room.detach(t.pid[5], now=now)                 # 长连接不通，改成轮询
        for i in range(1, 30):
            t.room.touch(t.pid[5], now=now + i * 1.5)
            t.room.sweep(now=now + i * 1.5)
            self.assertTrue(self.online(t, 5))
        t.room.sweep(now=now + 45 + game.OFFLINE_GRACE + 1)
        self.assertFalse(self.online(t, 5))              # 不来取了才算掉线

    def test_unseated_people_who_leave_the_lobby_are_forgotten(self):
        t = Table(D9)
        p = t.room.add_player('路人')
        now = time.time()
        t.room.attach(p['id'], now=now)
        t.room.detach(p['id'], now=now + 1)
        t.room.sweep(now=now + 2)
        self.assertIn(p['id'], t.room.players)           # 可能只是刷新了一下页面
        t.room.sweep(now=now + 60)
        self.assertNotIn(p['id'], t.room.players)

    def test_people_who_joined_but_never_connected_are_forgotten_too(self):
        t = Table(D9)
        ghost = t.room.add_player('没连上')
        seated = t.room.add_player('占了座但没连上')
        t.act(9, 'stand')
        t.room.action(seated['id'], 'sit', {'seat': 9})
        now = time.time()
        t.room.sweep(now=now + game.GHOST_AFTER - 5)
        self.assertIn(ghost['id'], t.room.players)        # 也许只是网慢
        t.room.sweep(now=now + game.GHOST_AFTER + 5)
        self.assertNotIn(ghost['id'], t.room.players)
        self.assertIn(seated['id'], t.room.players)       # 占着座位的人不动，由房主决定请不请离
        self.assertIn(t.host, t.room.players)

    def test_someone_who_was_offline_can_come_back_and_act(self):
        t = Table(D12)
        t.deal()
        t.drop(12)                                       # 守卫锁屏了
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {12: 'guard'})       # 轮到他了，他不在
        self.assertFalse(self.online(t, 12))
        t.room.attach(t.pid[12])                         # 拿起手机，页面连回来
        self.assertEqual(t.view(12)['night']['prompt']['type'], 'guard')
        t.act(12, 'night', targets=[5])
        t.flush()
        self.assertNotIn(12, t.types())                  # 守卫环节过去了，游戏继续

    def test_host_can_be_the_guard(self):
        """房主自己抽到守卫：「守卫请睁眼」播完，房主手机上就要出现守卫的操作界面。"""
        deck = ['guard'] + ['wolf'] * 3 + ['wolfking', 'mech', 'psychic', 'witch', 'hunter', 'knight'] + ['villager'] * 5
        t = Table(deck)
        t.deal()
        t.act(1, 'start_night')
        for _ in range(50):
            cues = t.view(1).get('cues') or []
            if cues and cues[0]['clips'] == ['guard_open']:
                break
            self.assertTrue(t.ack_one() or t.clock.run_next())
        self.assertIsNone(t.view(1)['night']['prompt'])  # 还在播「守卫请睁眼」，界面先不出来
        t.ack_one()                                      # 播完了
        pr = t.view(1)['night']['prompt']
        self.assertEqual((pr['type'], pr['ui']), ('guard', 'pick'))
        self.assertEqual(pr['targets'], list(range(1, 16)))
        t.act(1, 'night', targets=[1])                   # 守自己
        t.flush()
        self.assertEqual(t.g['night']['guard'], 1)

    def test_host_can_stop_waiting_for_a_dead_player_who_left(self):
        t = Table(D9)                                    # 9 号是猎人
        t.deal()
        t.night(kill=4)
        t.confirm_dead()
        t.act(1, 'start_vote')
        for s in t.day()['vote']['voters']:
            t.act(s, 'vote', target=9)
        t.flush()
        self.assertEqual(t.day()['settle']['waiting'], [9])       # 猎人被放逐，等他决定开不开枪
        t.drop(9)                                        # 他把手机一扔走了
        with self.assertRaises(GameError):
            t.act(2, 'settle_close')                     # 只有房主能不等
        t.act(1, 'settle_close')
        t.flush()
        self.assertEqual(t.stage(), 'dusk')              # 按不开枪处理，游戏继续
        self.assertEqual(len(t.alive()), 7)

    def test_not_waiting_for_a_dead_sheriff_tears_the_badge(self):
        t = Table(D9, sheriff=True)
        t.deal()
        t.night(kill=4)
        for s in t.day()['elect']['players']:
            t.act(s, 'elect_run', run=s == 4)
        t.flush()
        for _ in range(6):                               # 只有 4 号上警：一路点下去，直到他当选
            if t.g['sheriff']:
                break
            if t.stage() in ('e_speech', 'e_pk'):
                t.act(1, 'elect_next')
            elif t.stage() == 'e_withdraw':
                t.act(4, 'elect_withdraw', out=False)
            t.flush()
        self.assertEqual(t.g['sheriff'], 4)
        self.assertEqual(t.day()['settle']['waiting'], [4])       # 他昨晚被刀了，现在要决定警徽给谁
        t.act(1, 'settle_close')
        t.flush()
        self.assertEqual(t.g['sheriff'], 0)
        self.assertEqual(t.g['badge'], 'lost')
        self.assertEqual(t.stage(), 'discuss')

    def test_stalled_narration_can_be_taken_over_even_if_host_is_online(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')                          # 排上了「天黑请闭眼」，但房主手机一直没播完
        self.assertTrue(t.view(1)['cues'])
        with self.assertRaises(GameError):
            t.act(2, 'take_host')                        # 才刚开始，不算卡住
        t.room.sweep(now=time.time() + game.CUE_STALL - 5)
        self.assertFalse(t.view(2)['stalled'])
        t.room.sweep(now=time.time() + game.CUE_STALL + 30)
        self.assertTrue(t.view(2)['stalled'])
        self.assertTrue(t.view(2)['host_online'])
        t.act(2, 'take_host')
        v = t.view(2)
        self.assertTrue(v['you']['host'])
        self.assertFalse(v['stalled'])
        self.assertEqual(v['cues'][0]['clips'], ['night_fall'])   # 新房主从没播完的那一句接着播
        self.assertNotIn('cues', t.view(1))
        t.room.ack(t.pid[2], v['cues'][0]['id'])
        t.room.ack(t.pid[1], 999)                        # 原来那台手机迟到的回报不算数
        self.assertEqual(t.room.phase, 'night')

    def test_stalled_does_not_outlive_the_game_it_happened_in(self):
        t = Table(D9)
        t.deal()
        t.act(1, 'start_night')
        t.room.sweep(now=time.time() + game.CUE_STALL + 30)
        self.assertTrue(t.view(2)['stalled'])
        t.act(1, 'abort')                                # 房主结束了这一局
        self.assertFalse(t.view(2)['stalled'])           # 大厅里没有话要播，谈不上卡住
        with self.assertRaises(GameError):
            t.act(2, 'take_host')                        # 房主好好的，不能被人顺手拿走

    def test_long_announcements_get_more_time_before_counting_as_stalled(self):
        t = Table(D9)
        t.room.cue(['elect_list'] + ['n%d' % i for i in range(1, 16)])
        t.room.sweep(now=time.time() + game.CUE_STALL + 10)
        self.assertFalse(t.room.stalled)
        t.room.sweep(now=time.time() + game.CUE_STALL + 60)
        self.assertTrue(t.room.stalled)


class EdgeCases(unittest.TestCase):
    """审查时发现的边界情况，每一条都先复现出问题，修好以后留在这里防止回退。"""

    def test_claiming_a_seat_needs_the_hosts_ok(self):
        """知道房间号的人不能趁别人锁屏顶掉他的座位、看他的身份：认领要房主同意。"""
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid = t.room.request_claim(5, '新手机')
        self.assertEqual(t.room.claim_status(rid), ('wait', None))
        self.assertEqual(t.view(1)['claims'], [{'rid': rid, 'seat': 5, 'name': '新手机'}])
        self.assertNotIn('claims', t.view(2))                     # 只有房主看得到
        old = t.room.players[t.pid[5]]['token']
        with self.assertRaises(GameError):
            t.act(2, 'claim_ok', rid=rid)                          # 只有房主能同意
        self.assertEqual(t.room.players[t.pid[5]]['token'], old)
        revoked = []
        t.room.on_revoke = lambda room, pid: revoked.append(pid)
        t.act(1, 'claim_ok', rid=rid)
        self.assertEqual(t.room.claim_status(rid)[0], 'ok')
        self.assertIsNone(t.room.auth(t.pid[5], old))              # 旧手机的身份作废
        self.assertEqual(revoked, [t.pid[5]])                      # 并且让服务器掐断旧手机的连接
        self.assertEqual(t.view(1)['claims'], [])

    def test_a_claim_is_void_when_the_seat_comes_back_refused_or_old(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid = t.room.request_claim(5, '甲')
        t.room.attach(t.pid[5])                                    # 原来的手机回来了：只是锁屏了一会儿
        self.assertEqual(t.room.claim_status(rid)[0], 'no')
        self.assertEqual(t.view(1)['claims'], [])
        with self.assertRaises(GameError):
            t.act(1, 'claim_ok', rid=rid)
        t.drop(6)
        rid = t.room.request_claim(6, '乙')
        t.act(1, 'claim_no', rid=rid)
        self.assertEqual(t.room.claim_status(rid)[0], 'no')
        now = time.time()
        rid = t.room.request_claim(6, '丙', now=now)
        self.assertEqual(t.room.claim_status(rid, now=now + game.CLAIM_TTL + 1)[0], 'gone')
        self.assertEqual(t.room.claim_status('不存在')[0], 'gone')
        lobby = Table(D9)
        lobby.drop(5)
        with self.assertRaises(GameError):
            lobby.room.request_claim(5, '丁')                       # 还没发牌：直接选座位就行

    def test_an_approved_claim_id_stops_working_once_the_seat_is_claimed_again(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid1 = t.room.request_claim(5, '甲')
        t.act(1, 'claim_ok', rid=rid1)
        tok1 = t.room.claim_status(rid1)[1]['token']
        rid2 = t.room.request_claim(5, '乙')                       # 那台手机又丢了，再换一台
        t.act(1, 'claim_ok', rid=rid2)
        self.assertEqual(t.room.claim_status(rid1)[0], 'gone')     # 第一台手机拿旧编号取不到新身份
        st, p = t.room.claim_status(rid2)
        self.assertEqual(st, 'ok')
        self.assertNotEqual(p['token'], tok1)

    def test_a_claim_approved_just_before_it_expires_can_still_be_collected(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid = t.room.request_claim(5, '甲', now=time.time() - game.CLAIM_TTL + 5)    # 申请快 5 分钟了
        t.act(1, 'claim_ok', rid=rid)
        self.assertEqual(t.room.claim_status(rid, now=time.time() + 30)[0], 'ok')     # 批准以后重新计时
        self.assertEqual(t.room.claim_status(rid, now=time.time() + 20 * 60)[0], 'ok')  # 手机锁屏了二十分钟才拿起来
        self.assertEqual(t.room.claim_status(rid, now=time.time() + game.CLAIM_HOLD + 1)[0], 'gone')

    def test_only_the_newest_claim_for_a_seat_is_shown(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid1 = t.room.request_claim(5, '甲')
        rid2 = t.room.request_claim(5, '乙')
        self.assertEqual(t.room.claim_status(rid1)[0], 'no')
        self.assertEqual([c['rid'] for c in t.view(1)['claims']], [rid2])

    def test_cancelling_after_approval_still_hands_over_the_seat(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid = t.room.request_claim(5, '甲')
        t.act(1, 'claim_ok', rid=rid)
        st, p = t.room.cancel_claim(rid)                             # 撤回晚到了一步
        self.assertEqual((st, p['id']), ('ok', t.pid[5]))

    def test_repeat_claims_for_one_seat_do_not_block_other_seats(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        t.drop(9)
        for _ in range(30):                                        # 一直刷新认领页面，或者有人捣乱
            t.room.request_claim(5, '捣乱')
        rid = t.room.request_claim(9, '猎人')                      # 9 号照样能申请
        self.assertEqual(t.room.claim_status(rid)[0], 'wait')
        self.assertEqual(sorted(c['seat'] for c in t.view(1)['claims']), [5, 9])

    def test_claim_records_do_not_pile_up(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        for _ in range(500):                                       # 申请、撤回、再申请……
            t.room.cancel_claim(t.room.request_claim(5, '甲'))
        self.assertLessEqual(len(t.room.claims), game.CLAIM_KEEP)
        rid = t.room.request_claim(5, '甲')
        self.assertEqual(t.room.claim_status(rid)[0], 'wait')

    def test_an_unanswered_claim_disappears_from_the_host_when_it_expires(self):
        t = Table(D9)
        t.deal()
        t.drop(5)
        rid = t.room.request_claim(5, '甲', now=time.time() - game.CLAIM_TTL - 1)
        t.room.sweep()
        self.assertEqual(t.view(1)['claims'], [])
        with self.assertRaises(GameError):                         # 过期的横幅点同意也不会生效
            t.act(1, 'claim_ok', rid=rid)

    def test_kick_does_not_remove_a_newcomer_with_the_same_name(self):
        t = Table(D9)
        t.act(9, 'stand')
        p = t.room.add_player('玩家')
        t.room.attach(p['id'])
        t.room.action(p['id'], 'sit', {'seat': 9})
        seen = t.view(1)['seats'][8]                               # 房主点了 9 号，确认框打开
        t.room.action(p['id'], 'stand', {})
        q = t.room.add_player('玩家')                              # 另一个也叫「玩家」的人坐了上来
        t.room.attach(q['id'])
        t.room.action(q['id'], 'sit', {'seat': 9})
        with self.assertRaises(GameError):
            t.act(1, 'kick', seat=9, name=seen['name'], sat=seen['sat'])
        self.assertEqual(t.room.seat_map()[9]['id'], q['id'])
        now = t.view(1)['seats'][8]
        t.act(1, 'kick', seat=9, name=now['name'], sat=now['sat'])
        self.assertNotIn(9, t.room.seat_map())

    def test_whoever_takes_over_narration_cannot_approve_claims_for_other_seats(self):
        t = Table(D9)
        t.deal()
        t.drop(1)                                                  # 房主的手机没了
        t.act(2, 'take_host')                                      # 2 号接手播报
        t.drop(4)                                                  # 4 号锁屏
        rid = t.room.request_claim(4, '4号')                       # 2 号用另一台手机冒充 4 号
        self.assertEqual(t.view(2)['claims'], [])                  # 接手播报的人看不到这条申请
        with self.assertRaises(GameError):
            t.act(2, 'claim_ok', rid=rid)                          # 也批准不了
        with self.assertRaises(GameError):
            t.act(2, 'claim_no', rid=rid)
        self.assertEqual(t.room.claim_status(rid)[0], 'wait')
        with self.assertRaises(GameError):
            t.act(2, 'deal')                                       # 游戏中途点「发牌」也拿不到批准权
        with self.assertRaises(GameError):
            t.act(2, 'claim_ok', rid=rid)
        mine = t.room.request_claim(1, '房主')                     # 原来的房主借了一台手机回来：这个可以批准
        self.assertEqual([c['rid'] for c in t.view(2)['claims']], [mine])
        t.act(2, 'claim_ok', rid=mine)
        t.room.attach(t.pid[1])
        self.assertEqual([c['rid'] for c in t.view(1)['claims']], [rid])   # 由他来决定 4 号的申请
        t.act(1, 'claim_no', rid=rid)
        self.assertEqual(t.room.claim_status(rid)[0], 'no')

    def test_a_host_without_a_seat_hands_claims_to_whoever_narrates(self):
        t = Table(D9)
        t.act(1, 'stand')                                          # 房主不入座，只负责播报
        extra = t.room.add_player('玩家1')
        t.room.attach(extra['id'])
        t.room.action(extra['id'], 'sit', {'seat': 1})
        t.pid[1] = extra['id']
        t.room.action(t.host, 'deal', {})
        t.room.detach(t.host)
        t.room.sweep(now=time.time() + 60)
        t.act(2, 'take_host')
        t.drop(4)
        rid = t.room.request_claim(4, '4号')
        t.act(2, 'claim_ok', rid=rid)                              # 原来的房主回不来了，只能由现在播报的人处理
        self.assertEqual(t.room.claim_status(rid)[0], 'ok')

    def test_kick_only_removes_the_person_the_host_saw(self):
        t = Table(D9)
        with self.assertRaises(GameError):
            t.act(1, 'kick', seat=5, name='别人')                   # 确认框打开以后，座位上换了人
        self.assertIn(5, t.room.seat_map())
        t.act(1, 'kick', seat=5, name='玩家5')
        self.assertNotIn(5, t.room.seat_map())

    def test_not_waiting_only_covers_the_people_the_host_saw(self):
        deck = ['villager', 'wolfking', 'wolf', 'wolf', 'villager', 'villager', 'seer', 'witch', 'hunter']
        t = Table(deck)
        t.deal()
        t.night(kill=5)
        t.confirm_dead()
        t.act(1, 'start_vote')
        for s in t.day()['vote']['voters']:
            t.act(s, 'vote', target=9)
        t.flush()
        self.assertEqual(t.day()['settle']['waiting'], [9])        # 猎人被放逐
        t.act(9, 'settle', target=2)                               # 就在房主点「不等了」的那一刻，猎人带走了狼王
        self.assertEqual(t.day()['settle']['waiting'], [2])
        t.act(1, 'settle_close', seats=[9])                        # 房主点的时候屏幕上只有 9 号
        self.assertEqual(t.day()['settle']['waiting'], [2])        # 狼王的枪还在
        self.assertTrue(t.day(2)['settle']['mine']['can_shoot'])
        t.act(1, 'settle_close', seats=[2])
        t.flush()
        self.assertEqual(t.stage(), 'dusk')

    def _knight_sheriff(self):
        """9 号骑士当选警长，还没选发言顺序。"""
        deck = ['villager', 'wolf', 'wolf', 'wolf', 'villager', 'villager', 'seer', 'witch', 'knight']
        t = Table(deck, sheriff=True)
        t.deal()
        t.night(kill=0)
        for s in range(1, 10):
            t.act(s, 'elect_run', run=s == 9)
        t.flush()
        t.act(1, 'elect_next')
        t.act(9, 'elect_withdraw', out=False)
        t.flush()
        t.confirm_dead()
        self.assertEqual(t.g['sheriff'], 9)
        self.assertTrue(t.day(9)['order']['mine'])
        t.act(9, 'duel', target=5)                                 # 5 号是好人：骑士出局
        t.flush()
        self.assertEqual(t.day()['settle']['waiting'], [9])
        t.heard = []
        return t

    def test_knight_sheriff_who_loses_a_duel_before_choosing_the_order(self):
        t = self._knight_sheriff()
        t.act(9, 'settle', target=0, badge=0)                      # 撕掉警徽：没有警长了
        t.flush()
        d = t.day(2)
        self.assertEqual(d['stage'], 'discuss')
        self.assertNotIn('order', d)                               # 不能一直挂着「等警长选发言顺序」
        self.assertIsNotNone(d['speak'])
        self.assertIn('discuss', t.heard)
        sp = t.room.add_player('旁观')
        with self.assertRaises(GameError):
            t.room.action(sp['id'], 'order', {'i': 0})             # 没座位的人更不能替警长选

        t = self._knight_sheriff()
        t.act(9, 'settle', target=0, badge=7)                      # 警徽交给 7 号：由新警长选，从他两边开始
        t.flush()
        d = t.day(7)
        self.assertTrue(d['order']['mine'])
        self.assertEqual(d['order']['opts'], [{'start': 8, 'dir': 1}, {'start': 6, 'dir': -1}])
        self.assertIn('order_ask', t.heard)
        t.act(7, 'order', i=0)
        self.assertEqual(t.day()['speak'], {'start': 8, 'dir': 1})

    def test_mech_second_knife_alone_is_an_ordinary_knife(self):
        t = Table(board('mech', 'psychic', 'witch', 'hunter', 'guard'))
        t.deal()
        t.night(kill=0, mech=1)                                    # 学到狼人：一次双刀
        for w in (1, 2, 3):
            t.exile(w)
            if w != 3:
                t.night(kill=0)
        t.confirm_dead()
        t.act(1, 'start_night')
        t.flush()
        t.act(12, 'night', skip=True)                              # 守卫空守
        t.flush()
        t.act(4, 'night', ok=True)
        t.flush()
        t.act(4, 'wolf_pick', target=0)                            # 第一刀空着
        t.act(4, 'wolf_extra', target=6)                           # 只用了「第二刀」
        t.act(4, 'wolf_confirm')
        t.flush()
        pr = t.prompts()[10]
        self.assertEqual((pr['victim'], pr['can_save']), (6, True))  # 女巫看得到刀口，能救
        t.night(save=True)
        self.assertEqual(t.day()['night_deaths'], [])
        self.assertTrue(t.g['mech']['double'])                     # 双刀没有用掉

    def test_skip_only_skips_the_step_the_host_meant(self):
        t = Table(D12)                                             # 12 号守卫
        t.deal()
        t.act(1, 'start_night')
        t.flush()
        self.assertEqual(t.types(), {12: 'guard'})
        key = t.view(1)['skip_key']
        self.assertNotIn('skip_key', t.view(2))
        t.act(12, 'night', targets=[5])                            # 房主正在犹豫要不要跳过，守卫自己做完了
        t.flush()
        self.assertEqual(set(t.types().values()), {'wolf'})
        with self.assertRaises(GameError):
            t.act(1, 'skip', key=key)                              # 不能把狼人跳过去
        self.assertEqual(set(t.types().values()), {'wolf'})
        t.act(1, 'skip', key=t.view(1)['skip_key'])
        t.flush()
        self.assertNotIn('wolf', t.types().values())

    def test_dealing_clears_a_stalled_flag_from_the_lobby(self):
        t = Table(D9)
        t.act(1, 'test')                                           # 试音，但房主手机没播出来
        t.room.sweep(now=time.time() + game.CUE_STALL + 30)
        self.assertTrue(t.view(2)['stalled'])
        t.act(1, 'deal')
        self.assertFalse(t.view(2)['stalled'])                     # 「发牌」这一句才刚开始
        with self.assertRaises(GameError):
            t.act(2, 'take_host')

    def test_knight_card_matches_when_a_duel_is_allowed(self):
        self.assertIn('不含警长竞选和 PK', ROLES['knight']['desc'])


class Fuzz(unittest.TestCase):
    """随机打很多局：必须都能打完，而且语音和界面始终对得上。"""

    def play(self, roles, seed, sheriff, chaos=False):
        """chaos=True：一边打一边有人掉线、连回来、手机被冻住，房主掉线了就换人播报。"""
        r = random.Random(seed)
        t = Table(roles=full_roles(roles), seed=seed, sheriff=sheriff)
        t.act(1, 'deal')
        opened = [None]                      # 语音当前叫到的环节
        clock = [time.time()]                # chaos 用的假时间
        takeovers = [0]

        def host_seat():
            return t.room.players[t.room.host]['seat']

        def hear():
            cues = t.view(host_seat()).get('cues') or []
            if not cues:
                return False
            for c in cues[0]['clips']:
                if c.endswith('_open'):
                    opened[0] = c[:-5]
                elif c.endswith('_close'):
                    self.assertEqual(opened[0], c[:-6])
                    opened[0] = None
            t.heard += cues[0]['clips']
            t.room.ack(t.room.host, cues[0]['id'])
            return True

        def shake():
            """随机让一个人断线 / 连回来 / 回应心跳，时间往前走一点，再让房间检查一遍。"""
            pid = t.pid[r.choice(sorted(t.pid))]
            pl = t.room.players[pid]
            x = r.random()
            if pl['conns'] and x < 0.5:
                t.room.detach(pid, now=clock[0])
            elif not pl['conns']:
                t.room.attach(pid, hb=r.random() < 0.7, now=clock[0])
            else:
                t.room.touch(pid, now=clock[0])
            clock[0] += r.choice([0.5, 2, 5, 9, 20])
            for q in t.room.players.values():          # 大多数连着的手机会按时回应心跳
                if q['conns'] and r.random() < 0.85:
                    q['seen'] = clock[0]
            t.room.sweep(now=clock[0])
            if t.room.phase != 'lobby' and r.random() < 0.1:   # 有人换了手机，申请回到自己掉线的座位
                off = [x['seat'] for x in t.room.offline_seats()]
                if off:
                    rid = t.room.request_claim(r.choice(off), '')
                    who = [t.room.players[x]['seat'] for x in (t.room.host, t.room.owner) if t.room.players[x]['seat']]
                    if who and r.random() < 0.8:                      # 现在的房主或者发牌时的房主去处理
                        try:
                            t.act(r.choice(who), 'claim_ok' if r.random() < 0.6 else 'claim_no', rid=rid)
                        except GameError:
                            pass
            v = t.view(r.choice(sorted(t.pid)))
            if not v['host_online'] or v['stalled']:   # 播报停了：找一个在线的人接手
                online = [x['seat'] for x in v['seats'] if x['online'] and not x['host']]
                if online:
                    t.act(r.choice(online), 'take_host')
                    takeovers[0] += 1

        def night_move(s, pr):
            typ, ui = pr['type'], pr['ui']
            if ui in ('info', 'result'):
                return (s, 'night', {'ok': True})
            if ui == 'wolf':
                if pr.get('double') and r.random() < 0.5:
                    return (s, 'wolf_extra', {'target': r.choice([0] + pr['targets'])})
                if pr['agreed'] is not None and r.random() < 0.7:
                    return (s, 'wolf_confirm', {})
                lead = pr['picks'].get(min(pr['wolves']))
                target = lead if lead is not None and r.random() < 0.8 \
                    else r.choice([0] + pr['targets'])
                return (s, 'wolf_pick', {'target': target})
            if ui == 'witch':
                x = r.random()
                if pr['can_save'] and x < 0.5:
                    return (s, 'witch', {'save': True})
                if pr['poison'] and x < 0.8:
                    return (s, 'witch', {'poison': r.choice(pr['targets'])})
                return (s, 'witch', {})
            self.assertEqual(ui, 'pick')
            if len(pr['targets']) < pr['count'] or (pr['skip'] and r.random() < 0.25):
                self.assertTrue(pr['skip'], '%s 没有可选的人又不能跳过' % typ)
                return (s, 'night', {'skip': True})
            return (s, 'night', {'targets': r.sample(pr['targets'], pr['count'])})

        def moves():
            out = []
            ph = t.room.phase
            for s in t.pid:
                v = t.view(s)
                if ph == 'deal' and not v['deal']['seen']:
                    out.append((s, 'seen', {}))
                if ph == 'night' and v['night']['prompt']:
                    out.append(night_move(s, v['night']['prompt']))
                if ph != 'day':
                    continue
                d = v['day']
                me = v['me']
                mine = (d.get('settle') or {}).get('mine')
                if mine:
                    data = {'target': r.choice(d['settle']['targets'])
                            if mine['can_shoot'] and r.random() < 0.7 else 0}
                    if mine['badge']:
                        data['badge'] = r.choice([0] + d['settle']['targets'])
                    out.append((s, 'settle', data))
                if d.get('vote') and d['vote']['can']:
                    out.append((s, 'vote', {'target': r.choice([0] + d['vote']['cands'])}))
                e = d.get('elect')
                if e and e['mine'] == 'signup':
                    out.append((s, 'elect_run', {'run': r.random() < 0.4}))
                if e and e['mine'] == 'withdraw':
                    out.append((s, 'elect_withdraw', {'out': r.random() < 0.3}))
                if e and e['mine'] == 'vote':
                    out.append((s, 'elect_vote', {'target': r.choice([0] + e['vote']['cands'])}))
                if d.get('order') and d['order']['mine'] and r.random() < 0.5:
                    out.append((s, 'order', {'i': r.choice([0, 1])}))
                talking = d['stage'] in ('discuss', 'pk', 'e_speech', 'e_withdraw', 'e_pk')
                if talking and me['alive'] and me['team'] == 'wolf' \
                        and ROLES[me['role']].get('boom') and r.random() < 0.03:
                    others = [x['seat'] for x in v['seats'] if x['alive'] and x['seat'] != s]
                    out.append((s, 'boom', {'target': r.choice([0] + others)}))
                if d['stage'] == 'discuss' and me['alive'] and me['role'] == 'knight' \
                        and not t.g['knight_used'] and r.random() < 0.1:
                    others = [x['seat'] for x in v['seats'] if x['alive'] and x['seat'] != s]
                    out.append((s, 'duel', {'target': r.choice(others)}))
            hs = host_seat()
            v = t.view(hs)
            if ph == 'deal' and v['deal']['count'] == len(t.pid):
                out.append((hs, 'start_night', {}))
            if ph == 'day':
                stage = v['day']['stage']
                if stage in ('discuss', 'pk'):
                    out.append((hs, 'start_vote', {}))
                if stage == 'dusk':
                    out.append((hs, 'start_night', {}))
                if stage in ('e_speech', 'e_pk'):
                    out.append((hs, 'elect_next', {}))
            if chaos:
                # 房主的各种「不等了」：有人掉线时真实的房主就会这么点，而且常常点得不是时候
                if ph == 'night' and t.g['night']['sub'] == 'act' and r.random() < 0.12:
                    out.append((hs, 'skip', {}))
                if ph == 'day':
                    stage = v['day']['stage']
                    if stage in ('e_signup', 'e_withdraw', 'e_vote') and r.random() < 0.1:
                        out.append((hs, 'elect_close', {}))
                    if stage == 'vote' and r.random() < 0.1:
                        out.append((hs, 'end_vote', {}))
                    if stage == 'settle' and r.random() < 0.15:
                        out.append((hs, 'settle_close', {}))
            return out

        for _ in range(20000):
            if t.room.phase == 'over':
                break
            # 界面和语音必须对得上：有人手机上出现了某环节的操作，语音就一定正叫着这个环节
            for seat, typ in t.types().items():
                self.assertEqual(typ, opened[0], '第%d局 %s' % (seed, t.heard[-6:]))
                self.assertTrue(t.g['seats'][seat]['alive'])
            if chaos and r.random() < 0.3:
                shake()
            ms = moves()
            if ms and (r.random() < 0.5 or not (t.view(host_seat()).get('cues') or t.clock.queue)):
                s, typ, data = r.choice(ms)
                t.act(s, typ, **data)
            elif not hear():
                self.assertTrue(t.clock.run_next() or ms,
                                '第%d局卡死：%s %s' % (seed, t.room.phase, t.stage()))
        self.assertEqual(t.room.phase, 'over', '第%d局没打完' % seed)
        while hear() or t.clock.run_next():
            pass
        self.assertIn(t.heard[-1], ('win_good', 'win_wolf', 'win_third'))
        self.takeovers = getattr(self, 'takeovers', 0) + takeovers[0]

        # 每一夜的语音顺序都必须是规定的顺序
        step_clips = set(['night_fall', 'day_break'])
        for step, _need, _when in NIGHT_STEPS:
            step_clips.update(step + x for x in ('_open', '_prompt', '_close'))
        seq = [c for c in t.heard if c in step_clips]
        nights, cur = [], None
        for c in seq:
            if c == 'night_fall':
                cur = [c]
                nights.append(cur)
            else:
                cur.append(c)
        for i, got in enumerate(nights):
            steps = night_steps(full_roles(roles), i + 1)
            want = ['night_fall'] + [s + x for s in steps
                                     for x in ('_open', '_prompt', '_close')] + ['day_break']
            self.assertEqual(got, want, '第%d局第%d夜' % (seed, i + 1))
        return t.g['winner']

    def test_random_games(self):
        wins = {}
        for i, preset in enumerate(PRESETS):
            for seed in range(24):
                w = self.play(preset['roles'], seed * 100 + i, sheriff=seed % 2 == 0)
                wins[w] = wins.get(w, 0) + 1
        self.assertGreater(wins.get('good', 0), 0)
        self.assertGreater(wins.get('wolf', 0), 0)

    def test_random_games_with_everything_at_once(self):
        roles = dict(wolf=1, wolfking=1, whitewolf=1, beauty=1, nightmare=1, mech=1, gargoyle=1,
                     villager=3, seer=1, witch=1, hunter=1, guard=1, knight=1, dreamer=1,
                     magician=1, cupid=1)
        for seed in range(40):
            self.play(roles, 7000 + seed, sheriff=True)
        roles = dict(wolf=2, bloodmoon=1, ghostrider=1, villager=4, seer=1, witch=1, idiot=1,
                     witcher=1, psychic=1, gravekeeper=1, cupid=1, hunter=1)
        for seed in range(40):
            self.play(roles, 9000 + seed, sheriff=True)
        # 混血儿和丘比特、机械狼、骑士、猎魔人、守墓人在同一局
        roles = dict(wolf=2, wolfking=1, mech=1, villager=3, seer=1, witch=1, knight=1, gravekeeper=1,
                     witcher=1, cupid=1, mixed=1)
        for seed in range(40):
            self.play(roles, 9500 + seed, sheriff=True)

    def test_15_player_board_with_people_dropping_all_the_time(self):
        """15 人 通灵师女巫猎人守卫骑士 + 狼王机械狼：不停有人掉线、换人播报，也必须每局都能打完。"""
        roles = dict(wolf=3, wolfking=1, mech=1, villager=5, psychic=1, witch=1, hunter=1, guard=1, knight=1)
        for seed in range(40):
            self.play(roles, 15000 + seed, sheriff=seed % 2 == 0, chaos=True)
        self.assertGreater(self.takeovers, 0)          # 确实测到了「换一台手机播报」
        mixed = dict(roles, villager=4, mixed=1)       # 同一个板子拿一张村民换成混血儿
        for seed in range(20):
            self.play(mixed, 15500 + seed, sheriff=seed % 2 == 0, chaos=True)
        for i, preset in enumerate(PRESETS):
            for k in range(3):
                self.play(preset['roles'], 16000 + i * 10 + k, sheriff=k != 1, chaos=True)
        # 所有角色混在一起，再加上掉线和房主乱点「不等了」
        roles = dict(wolf=1, wolfking=1, whitewolf=1, beauty=1, nightmare=1, mech=1, gargoyle=1,
                     villager=3, seer=1, witch=1, hunter=1, guard=1, knight=1, dreamer=1,
                     magician=1, cupid=1)
        for seed in range(30):
            self.play(roles, 17000 + seed, sheriff=True, chaos=True)
        roles = dict(wolf=2, bloodmoon=1, ghostrider=1, villager=4, seer=1, witch=1, idiot=1,
                     witcher=1, psychic=1, gravekeeper=1, cupid=1, hunter=1)
        for seed in range(30):
            self.play(roles, 18000 + seed, sheriff=True, chaos=True)


if __name__ == '__main__':
    unittest.main()
