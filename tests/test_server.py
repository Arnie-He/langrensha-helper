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
        cls.saved = (server.PING_EVERY, server.SWEEP_EVERY, server.DEV, game.OFFLINE_GRACE, game.ALIVE_FOR,
                     server.Handler.timeout)
        server.PING_EVERY, server.SWEEP_EVERY, server.DEV = PING, 0.05, True
        server.Handler.timeout = 1.5
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
        (server.PING_EVERY, server.SWEEP_EVERY, server.DEV, game.OFFLINE_GRACE, game.ALIVE_FOR,
         server.Handler.timeout) = cls.saved

    def setUp(self):
        self.streams = []
        server.hits.clear()                                      # 频率限制按测试分开算

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

    def game6(self):
        """6 人局：甲是房主坐 1 号，另外 5 人依次入座，全部连上以后发牌。"""
        a = post(self.port, '/api/create', {'name': '甲', 'roles': {'wolf': 2, 'villager': 2, 'seer': 1, 'witch': 1}})
        creds = [a] + [post(self.port, '/api/join', {'code': a['code'], 'name': '玩家%d' % i}) for i in range(2, 7)]
        for i, c in enumerate(creds):
            self.act(c, 'sit', seat=i + 1)
        streams = [self.open(c) for c in creds]
        self.assertTrue(until(lambda: all(x.view and x.view['seats'][5]['online'] for x in streams[:1])))
        self.assertTrue(until(lambda: self.act(a, 'deal').get('ok')))
        return creds, streams

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

    def test_claiming_a_seat_needs_the_host_and_cuts_off_the_old_phone(self):
        creds, streams = self.game6()
        a, b = creds[0], creds[1]
        frozen = self.open(b, hb=True)                           # 2 号手机：锁屏了，连接还开着，但不回应心跳
        self.assertTrue(until(lambda: frozen.view))
        streams[1].cut()
        self.assertTrue(until(lambda: not streams[0].view['seats'][1]['online'], ALIVE * 4))
        j = post(self.port, '/api/join', {'code': a['code'], 'name': '旁人'})
        self.assertEqual([x['seat'] for x in j['claim']], [2])
        r = post(self.port, '/api/claim', {'code': a['code'], 'seat': 2, 'name': '旁人'})
        self.assertEqual(r['state'], 'wait')
        self.assertNotIn('pid', r)                               # 没有房主同意，拿不到这个座位的身份
        rid = r['rid']
        self.assertEqual(post(self.port, '/api/claim', {'code': a['code'], 'rid': rid})['state'], 'wait')
        self.assertTrue(until(lambda: streams[0].view.get('claims')))
        self.assertEqual(streams[0].view['claims'][0]['seat'], 2)
        self.assertNotIn('claims', streams[2].view)
        self.assertEqual(self.act(b, 'claim_ok', rid=rid).get('status'), 400)   # 只有房主能同意
        self.assertTrue(self.act(a, 'claim_ok', rid=rid).get('ok'))
        c = post(self.port, '/api/claim', {'code': a['code'], 'rid': rid})
        self.assertEqual(c['pid'], b['pid'])
        self.assertNotEqual(c['token'], b['token'])
        self.assertTrue(until(lambda: frozen.closed))           # 旧手机上还开着的连接被掐断，收不到这个座位的私密信息了
        self.assertEqual(get(self.port, '/api/view?' + self.qs(b))['status'], 404)
        self.assertEqual(get(self.port, '/api/view?' + self.qs(c))['you']['seat'], 2)

    def test_an_oversized_request_closes_the_connection(self):
        """请求体太大、没有读：这条连接必须关掉，否则剩下的字节会被当成下一个请求执行。"""
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        sock.sendall(b'POST /api/act HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n'
                     b'Content-Length: 70000\r\n\r\nGET /healthz HTTP/1.1\r\nHost: x\r\n\r\n')
        data = b''
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass
        sock.close()
        self.assertIn(b' 413 ', data.split(b'\r\n')[0])
        self.assertEqual(data.count(b'HTTP/1.1 '), 1)

    def test_requests_have_a_timeout_in_production(self):
        self.assertTrue(self.saved[5] and 0 < self.saved[5] <= 300)   # 没有超时的话，一走了之的手机会永远占着一个线程

    def test_idle_connections_are_closed(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=10)
        t0 = time.time()
        self.assertEqual(sock.recv(10), b'')                     # 什么都不发：一会儿以后服务器自己关掉
        self.assertLess(time.time() - t0, 5)
        sock.close()

    def test_dev_switch_only_turns_on_for_yes_values(self):
        try:
            for v, want in (('1', True), ('true', True), ('YES', True), ('0', False), ('', False), ('no', False)):
                os.environ['LRS_TEST_FLAG'] = v
                self.assertEqual(server.flag('LRS_TEST_FLAG'), want, v)
        finally:
            os.environ.pop('LRS_TEST_FLAG', None)

    def test_room_creation_cannot_be_exhausted(self):
        saved, made = server.MAX_ROOMS, []
        server.MAX_ROOMS = len(server.rooms) + 3
        try:
            for _ in range(3):
                made.append(server.new_room().code)
            with self.assertRaises(game.GameError):
                server.new_room()                                # 满了：报错，而不是卡死
            server.rooms[made[0]].touched -= 3600                # 有个房间很久没人动了：清掉，给新房间腾地方
            made.append(server.new_room().code)
            self.assertNotIn(made[0], server.rooms)
        finally:
            server.MAX_ROOMS = saved
            for c in made:
                server.rooms.pop(c, None)
                server.conns.pop(c, None)

    def test_creating_rooms_is_rate_limited_per_address(self):
        saved, server.CREATE_LIMIT = server.CREATE_LIMIT, (3, 60)
        try:
            for _ in range(3):
                self.assertIn('pid', post(self.port, '/api/create', {'name': '甲'}))
            self.assertEqual(post(self.port, '/api/create', {'name': '甲'})['status'], 429)
        finally:
            server.CREATE_LIMIT = saved

    def test_claim_requests_are_rate_limited_per_address(self):
        creds, streams = self.game6()
        streams[1].cut()
        self.assertTrue(until(lambda: not streams[0].view['seats'][1]['online'], ALIVE * 4))
        saved, server.CLAIM_LIMIT = server.CLAIM_LIMIT, (2, 60)
        try:
            for _ in range(2):
                self.assertEqual(post(self.port, '/api/claim', {'code': creds[0]['code'], 'seat': 2})['state'], 'wait')
            self.assertEqual(post(self.port, '/api/claim', {'code': creds[0]['code'], 'seat': 2})['status'], 429)
        finally:
            server.CLAIM_LIMIT = saved

    def test_a_full_server_drops_rooms_nobody_ever_used_first(self):
        saved, made = server.MAX_ROOMS, []
        server.MAX_ROOMS = len(server.rooms) + 2
        try:
            for _ in range(2):
                made.append(server.new_room().code)
            for c in made:
                server.rooms[c].created -= 120                   # 刷出来的空房间：一分钟以上没人连过
            made.append(server.new_room().code)                  # 满了也不报错：先清掉这种房间
            self.assertEqual(sum(1 for c in made if c in server.rooms), 2)
        finally:
            server.MAX_ROOMS = saved
            for c in made:
                server.rooms.pop(c, None)
                server.conns.pop(c, None)

    def test_bad_credentials_are_rejected(self):
        a, b = self.room()
        self.assertEqual(get(self.port, '/api/view?code=%s&pid=%s&token=nope' % (a['code'], a['pid']))['status'], 404)
        self.assertEqual(post(self.port, '/api/beat', dict(a, token='nope'))['status'], 403)
        self.assertEqual(post(self.port, '/api/beat', dict(a, code='9999x'))['status'], 404)


if __name__ == '__main__':
    unittest.main()
