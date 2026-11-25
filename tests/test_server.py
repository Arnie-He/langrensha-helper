# -*- coding: utf-8 -*-
"""服务器测试：真的起一个服务器，用真的连接去连，重点测掉线和重连。

运行： python3 -m unittest discover -s tests
为了跑得快，把心跳间隔、掉线宽限期都调短了（正式值见 server.py / game.py 开头）。
"""
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import game  # noqa: E402
import server  # noqa: E402

PING, GRACE, ALIVE = 0.25, 0.8, 1.2


class Stream(threading.Thread):
    """一条实时连接（手机上的 EventSource）。可以随时掐断，也可以选择回不回应心跳。"""

    def __init__(self, port, cred, hb=False, beat=False):
        threading.Thread.__init__(self)
        self.daemon = True
        self.port, self.cred, self.beat = port, cred, beat
        self.views, self.pings, self.closed = [], 0, False
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=10)
        path = '/api/events?%scode=%s&pid=%s&token=%s' % ('hb=1&' if hb else '', cred['code'], cred['pid'], cred['token'])
        self.sock.sendall(('GET %s HTTP/1.1\r\nHost: x\r\n\r\n' % path).encode())
        self.start()

    def run(self):
        ev = ''
        try:
            for raw in self.sock.makefile('rb'):
                line = raw.decode('utf-8').rstrip('\r\n')
                if line.startswith('event: '):
                    ev = line[7:]
                elif line.startswith('data: '):
                    if ev == 'ping':
                        self.pings += 1
                        if self.beat:
                            post(self.port, '/api/beat', self.cred)
                    else:
                        self.views.append(json.loads(line[6:]))
                    ev = ''
        except (OSError, ValueError):
            pass
        self.closed = True

    def cut(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    @property
    def view(self):
        return self.views[-1] if self.views else None


def post(port, path, body):
    req = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), json.dumps(body).encode('utf-8'),
                                 {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return dict(json.loads(e.read().decode('utf-8') or '{}'), status=e.code)


def get(port, path):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d%s' % (port, path), timeout=5) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return dict(json.loads(e.read().decode('utf-8') or '{}'), status=e.code)


def until(cond, sec=4.0):
    end = time.time() + sec
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return bool(cond())


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = (server.PING_EVERY, server.SWEEP_EVERY, server.DEV, game.OFFLINE_GRACE, game.ALIVE_FOR)
        server.PING_EVERY, server.SWEEP_EVERY, server.DEV = PING, 0.05, True
        game.OFFLINE_GRACE, game.ALIVE_FOR = GRACE, ALIVE
        cls.srv = server.start(port=0)
        cls.port = cls.srv.server_address[1]
        t = threading.Thread(target=cls.srv.serve_forever)
        t.daemon = True
        t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        server.PING_EVERY, server.SWEEP_EVERY, server.DEV, game.OFFLINE_GRACE, game.ALIVE_FOR = cls.saved

    def setUp(self):
        self.streams = []

    def tearDown(self):
        for s in self.streams:
            s.cut()

    # -- 小工具
    def room(self):
        """建一个房间：甲是房主坐 1 号，乙坐 2 号。返回 (甲, 乙) 的身份。"""
        a = post(self.port, '/api/create', {'name': '甲'})
        b = post(self.port, '/api/join', {'code': a['code'], 'name': '乙'})
        self.act(a, 'sit', seat=1)
        self.act(b, 'sit', seat=2)
        return a, b

    def act(self, cred, typ, **data):
        return post(self.port, '/api/act', dict(cred, type=typ, data=data))

    def open(self, cred, **kw):
        s = Stream(self.port, cred, **kw)
        self.streams.append(s)
        return s

    def seat2(self, s):
        return s.view['seats'][1]['online']

    def qs(self, cred):
        return 'code=%s&pid=%s&token=%s' % (cred['code'], cred['pid'], cred['token'])

    # -- 测试
    def test_a_new_connection_gets_the_current_view_at_once_and_then_heartbeats(self):
        a, b = self.room()
        sa = self.open(a)
        self.assertTrue(until(lambda: sa.view))
        self.assertEqual(sa.view['phase'], 'lobby')
        self.assertTrue(sa.view['you']['host'])
        self.assertTrue(until(lambda: sa.pings >= 2))            # 心跳是真正的事件，手机端收得到

    def test_a_quick_reconnect_is_invisible_to_everyone_else(self):
        a, b = self.room()
        sa, sb = self.open(a), self.open(b)
        self.assertTrue(until(lambda: sa.view and self.seat2(sa)))
        seen = len(sa.views)
        for _ in range(4):                                       # 乙的连接断了又连，来回四次
            sb.cut()
            time.sleep(GRACE / 4)
            sb = self.open(b)
            self.assertTrue(until(lambda: sb.view))              # 每次连上都马上拿到画面
        time.sleep(GRACE * 1.5)
        self.assertEqual(sa.views[seen:], [])                    # 甲的手机一次多余的重画都没有，更没见到「掉线」
        self.assertTrue(self.seat2(sa))

    def test_offline_shows_after_the_grace_period_and_clears_on_return(self):
        a, b = self.room()
        sa, sb = self.open(a), self.open(b)
        self.assertTrue(until(lambda: sa.view and self.seat2(sa)))
        sb.cut()
        time.sleep(GRACE / 2)
        self.assertTrue(self.seat2(sa))
        self.assertTrue(until(lambda: not self.seat2(sa)))
        self.open(b)
        self.assertTrue(until(lambda: self.seat2(sa)))

    def test_a_frozen_page_is_marked_offline_until_it_answers_again(self):
        a, b = self.room()
        sa = self.open(a)
        sb = self.open(b, hb=True)                               # 新版页面，但被系统冻住了：连着，不回应心跳
        self.assertTrue(until(lambda: sa.view and self.seat2(sa)))
        self.assertTrue(until(lambda: not self.seat2(sa), ALIVE * 3))
        self.assertFalse(sb.closed)                              # 连接其实一直没断
        post(self.port, '/api/beat', b)                          # 醒过来了
        self.assertTrue(until(lambda: self.seat2(sa)))

    def test_a_page_that_answers_heartbeats_stays_online(self):
        a, b = self.room()
        sa = self.open(a)
        self.open(b, hb=True, beat=True)
        self.assertTrue(until(lambda: sa.view and self.seat2(sa)))
        seen = len(sa.views)
        time.sleep(ALIVE * 2.5)
        self.assertEqual(sa.views[seen:], [])                    # 一直在线，没有任何变化
        self.assertTrue(self.seat2(sa))

    def test_polling_works_when_live_connections_do_not(self):
        a, b = self.room()
        sa = self.open(a)
        self.assertTrue(until(lambda: sa.view))
        end = time.time() + GRACE * 2.5
        while time.time() < end:                                 # 乙连不上长连接，只能隔一会儿来取一次
            v = get(self.port, '/api/view?' + self.qs(b))
            self.assertEqual(v['you']['seat'], 2)
            time.sleep(GRACE / 4)
        self.assertTrue(self.seat2(sa))
        self.act(a, 'config', sheriff=False)                     # 取到的是最新的
        self.assertFalse(get(self.port, '/api/view?' + self.qs(b))['config']['sheriff'])
        self.assertTrue(until(lambda: not self.seat2(sa)))       # 不来取了，过了宽限期才算掉线

    def test_a_silently_dead_connection_can_be_recovered_by_fetching_the_view(self):
        a, b = self.room()
        sa = self.open(a)
        self.assertTrue(until(lambda: sa.view))
        get(self.port, '/api/debug?act=stall&sec=30&code=%s&pid=%s' % (a['code'], a['pid']))
        seen, pings = len(sa.views), sa.pings
        self.act(a, 'config', sheriff=False)
        time.sleep(PING * 4)
        self.assertEqual(len(sa.views), seen)                    # 连接「假活着」：没断，但什么都收不到
        self.assertLessEqual(sa.pings, pings + 1)                # 连心跳也没有了，手机端据此发现
        self.assertFalse(sa.closed)
        self.assertFalse(get(self.port, '/api/view?' + self.qs(a))['config']['sheriff'])
        sa2 = self.open(a)                                       # 换一条新连接就好了
        self.assertTrue(until(lambda: sa2.view and not sa2.view['config']['sheriff']))

    def test_one_player_whose_view_breaks_does_not_stop_the_others(self):
        a, b = self.room()
        sa, sb = self.open(a), self.open(b)
        self.assertTrue(until(lambda: sa.view and sb.view))
        room = server.rooms[a['code']]
        real = room.view

        def flaky_view(pid):
            if pid == b['pid']:
                raise RuntimeError('故意出错')
            return real(pid)
        room.view = flaky_view
        err, sys.stderr = sys.stderr, open(os.devnull, 'w')      # 这里会打印一段错误日志，测试时不用看
        try:
            self.assertTrue(self.act(a, 'config', sheriff=False).get('ok'))
            self.assertTrue(until(lambda: not sa.view['config']['sheriff']))
            self.assertEqual(get(self.port, '/api/view?' + self.qs(b))['status'], 500)
        finally:
            sys.stderr.close()
            sys.stderr = err
            room.view = real

    def test_bad_credentials_are_rejected(self):
        a, b = self.room()
        self.assertEqual(get(self.port, '/api/view?code=%s&pid=%s&token=nope' % (a['code'], a['pid']))['status'], 404)
        self.assertEqual(post(self.port, '/api/beat', dict(a, token='nope'))['status'], 403)
        self.assertEqual(post(self.port, '/api/beat', dict(a, code='9999x'))['status'], 404)


if __name__ == '__main__':
    unittest.main()
