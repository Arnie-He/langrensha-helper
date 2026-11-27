#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""狼人杀面杀助手 —— 服务器。

只用 Python 标准库，不需要安装任何东西：

    python3 server.py

默认端口 3210，可以用环境变量 PORT 修改。
手机和服务器之间用 SSE（服务器推送）+ 普通 POST 请求通信。
"""
import json
import os
import queue
import random
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import qr
import game
from game import GameError, PRESETS, ROLES, ROLE_ORDER, Room, clean_name, full_roles

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, 'public')
PORT = int(os.environ.get('PORT', '3210'))


def flag(name):
    """环境变量开关：只有 1 / true / yes / on 算打开（LRS_DEV=0 是关）。"""
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


DEV = flag('LRS_DEV')        # 开发时设 LRS_DEV=1：图片不缓存，改完马上能看到；还会打开 /api/debug（能看到所有人的身份）
ROOM_TTL = 6 * 3600          # 房间 6 小时没人动就清掉
PING_EVERY = 5               # 每 5 秒给每台手机发一次心跳；手机收到后回应一下，两边都能发现连接是不是真的还通
SWEEP_EVERY = 2              # 每 2 秒检查一遍谁真的掉线了、播报有没有卡住
WRITE_TIMEOUT = 20           # 往一台手机发数据，这么久发不出去就当它断了
IDLE_TIMEOUT = 60            # 普通请求的连接这么久没动静就关掉（手机一走了之时，不能让它一直占着一个线程）
MAX_ROOMS = 3000             # 同时最多这么多个房间
CREATE_LIMIT = (20, 600)     # 同一个地址 10 分钟内最多建 20 个房间
CLAIM_LIMIT = (10, 60)       # 同一个地址 1 分钟内最多提交 10 次认领座位的申请

TYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
    '.ico': 'image/x-icon', '.woff2': 'font/woff2',
    '.m4a': 'audio/mp4', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
}

rooms = {}
rooms_lock = threading.Lock()
conns = {}                   # 房间号 -> [连接]；每个连接是 {'pid', 'q', 'last'}
diags = {}                   # 仅开发模式：(房间号, 玩家) -> 手机上报的调试信息
muted = {}                   # 仅开发模式：(房间号, 玩家) -> 到什么时候为止，这个人的长连接一律收不到东西


def oops():
    """不该发生的错误：记到日志里（托管平台的日志页能看到），但不能让一个人的问题拖垮整个房间。"""
    traceback.print_exc()
    sys.stderr.flush()


class FixedDeck(random.SystemRandom):
    """仅供测试：环境变量 LRS_DECK 按座位号指定发牌结果，例如
    LRS_DECK=guard,wolf,witch,seer,... 。牌的组成和板子对不上时照常随机。"""

    def shuffle(self, x, *args):
        deck = [r.strip() for r in os.environ.get('LRS_DECK', '').split(',')]
        if sorted(deck) == sorted(x):
            x[:] = deck
        else:
            random.SystemRandom.shuffle(self, x)


def broadcast(room):
    """房间状态变了：给每台连着的手机推送它自己该看到的内容。"""
    for c in list(conns.get(room.code, [])):
        try:
            view = room.view(c['pid'])
            if view is None:
                continue
            msg = json.dumps(view, ensure_ascii=False, separators=(',', ':'))
        except Exception:               # 某一个人的画面算不出来，不能连累其他人收不到
            oops()
            continue
        if msg != c['last']:
            c['last'] = msg
            c['q'].put(msg)


def sweeper():
    """后台线程：定时让每个房间检查掉线和播报卡住。"""
    while True:
        time.sleep(SWEEP_EVERY)
        for room in list(rooms.values()):
            try:
                room.sweep()
            except Exception:
                oops()


hits = {}                    # (用途, 地址) -> 最近几次的时间
hits_lock = threading.Lock()


def too_many(kind, addr, limit):
    """同一个地址在一段时间内做某件事的次数超过上限了吗（顺便记一次）。"""
    n, per = limit
    now = time.time()
    with hits_lock:
        if len(hits) > 20000:                       # 别让这张表无限长
            for k in [k for k, v in hits.items() if not v or now - v[-1] > per]:
                del hits[k]
        q = [t for t in hits.get((kind, addr), []) if now - t < per]
        if len(q) >= n:
            hits[(kind, addr)] = q
            return True
        q.append(now)
        hits[(kind, addr)] = q
        return False


def revoke(room, pid):
    """某人的座位被新手机认领走了：掐断他旧手机上还开着的连接，免得那边继续收到这个座位的私密信息。"""
    for c in list(conns.get(room.code, [])):
        if c['pid'] == pid:
            c['drop'] = True


def new_room():
    with rooms_lock:
        now = time.time()
        for code in [k for k, r in rooms.items()
                     if now - r.touched > ROOM_TTL and not conns.get(k)]:
            del rooms[code]
            conns.pop(code, None)
        if len(rooms) >= MAX_ROOMS:
            # 房间太多（多半是有人在刷）：先清掉从来没有人连上过的空房间（建了一分钟以上），
            # 再清十分钟没人动、也没人连着的房间，最旧的先清
            def never_used(r):
                return now - r.created > 60 and not any(p['seen'] or p['conns'] for p in r.players.values())
            junk = sorted((r.touched, k) for k, r in rooms.items() if not conns.get(k) and never_used(r))
            idle = sorted((r.touched, k) for k, r in rooms.items()
                          if now - r.touched > 600 and not conns.get(k) and not never_used(r))
            for _, code in (junk + idle)[:len(rooms) - MAX_ROOMS + 1]:
                del rooms[code]
                conns.pop(code, None)
            if len(rooms) >= MAX_ROOMS:
                raise GameError('服务器上的房间太多了，请稍后再试')
        rnd = random.SystemRandom()
        code = None
        for _ in range(100):
            c = '%04d' % rnd.randrange(10000)
            if c not in rooms:
                code = c
                break
        if code is None:                                    # 随机碰不到空号，就按顺序找一个
            code = next('%04d' % i for i in range(10000) if '%04d' % i not in rooms)
        room = Room(code, on_change=broadcast, on_revoke=revoke,
                    rng=FixedDeck() if os.environ.get('LRS_DECK') else None)
        rooms[code] = room
        conns[code] = []
        return room


def lan_url():
    """这台电脑在局域网里的地址，给同一个 Wi-Fi 下的手机用。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))      # 不会真的发包，只是让系统选出网卡
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith('127.'):
            return 'http://%s:%d' % (ip, PORT)
    except OSError:
        pass
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'lrs'
    timeout = IDLE_TIMEOUT

    def log_message(self, fmt, *args):
        pass

    # -------------------------------------------------------------- 输出

    def send_bytes(self, status, body, ctype, cache='no-cache', etag=None):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        if etag:
            self.send_header('ETag', etag)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def send_json(self, obj, status=200):
        self.send_bytes(status, json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                        TYPES['.json'])

    def fail(self, msg, status=400):
        self.send_json({'error': msg}, status)

    def addr(self):
        """对方的地址。只有确定在托管平台的代理后面（Render 会设置 RENDER 环境变量）时才看 X-Forwarded-For，
        而且只用代理加上的最后一个（前面的可能是伪造的）；否则这个头谁都能随便填。"""
        if os.environ.get('RENDER') or flag('LRS_PROXY'):
            xff = [x.strip() for x in (self.headers.get('X-Forwarded-For') or '').split(',') if x.strip()]
            if xff:
                return xff[-1]
        return self.client_address[0]

    # -------------------------------------------------------------- GET

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
            pass
        except Exception:
            oops()
            try:
                self.fail('服务器出错了，请再试一次', 500)
            except OSError:
                pass

    def get(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == '/api/events':
            return self.events(q)
        if url.path == '/api/view':
            # 实时连接在某些网络下不通时，手机改成每隔一两秒来取一次画面
            room = rooms.get(q.get('code', ''))
            p = room and room.auth(q.get('pid'), q.get('token'))
            if not p:
                return self.fail('房间不存在或已失效', 404)
            room.touch(p['id'])
            return self.send_json(room.view(p['id']))
        if DEV and url.path == '/api/debug':
            return self.debug(q)
        if url.path == '/api/info':
            return self.send_json({
                'lan': lan_url(), 'presets': PRESETS,
                'roles': [dict(ROLES[r], id=r) for r in ROLE_ORDER],
            })
        if url.path == '/healthz':               # 托管平台用来确认服务还活着
            return self.send_bytes(200, b'ok', 'text/plain')
        if url.path == '/api/qr':
            try:
                body = qr.svg(q.get('t', '')[:200]).encode('utf-8')
            except ValueError:
                return self.fail('内容太长')
            return self.send_bytes(200, body, TYPES['.svg'])
        self.static(url.path)

    do_HEAD = do_GET

    def debug(self, q):
        """仅开发时可用（LRS_DEV=1），用来模拟网络故障：
        act=stall  某个人现有的实时连接「假活着」sec 秒：连接不断，但什么都收不到
        act=mute   sec 秒内这个人的实时连接（包括新连上来的）一律收不到东西：模拟长连接根本不通的网络
        act=drop   服务器这边直接掐断某个人的实时连接
        act=state  服务器眼里这个房间现在的样子
        用 pid= 或 seat= 指定是谁，都不给就是房主。"""
        room = rooms.get(q.get('code', ''))
        if not room:
            return self.fail('房间不存在', 404)
        if q.get('act') == 'state':                 # 服务器眼里这个房间现在的样子
            g, now = room.g or {}, time.time()
            nt, day = g.get('night') or {}, g.get('day') or {}
            return self.send_json({
                'phase': room.phase, 'night_no': g.get('night_no'),
                'night': {'idx': nt.get('idx'), 'sub': nt.get('sub'), 'steps': nt.get('steps')} if nt else None,
                'day': day.get('stage'), 'stalled': room.stalled,
                'cues': [[c['id'], c['clips']] for c in room.cues], 'cue_age': round(now - room.cue_since, 1),
                'host': room.players.get(room.host, {}).get('seat'),
                'players': [{'seat': x['seat'], 'name': x['name'], 'online': x['online'], 'conns': x['conns'],
                             'quiet': round(now - x['seen'], 1), 'role': (g.get('seats') or {}).get(x['seat'], {}).get('role'),
                             'alive': (g.get('seats') or {}).get(x['seat'], {}).get('alive'),
                             'diag': diags.get((room.code, x['id']))}
                            for x in sorted(room.players.values(), key=lambda x: x['seat'])],
                'conns': len(conns.get(room.code, [])), 'threads': threading.active_count()})
        pid = q.get('pid') or room.host
        seat = int(q.get('seat') or 0)
        if seat:
            pid = next((x['id'] for x in room.players.values() if x['seat'] == seat), pid)
        hit = 0
        for c in list(conns.get(room.code, [])):
            if c['pid'] != pid:
                continue
            hit += 1
            if q.get('act') == 'drop':
                c['drop'] = True
            elif q.get('act') == 'stall':
                c['stall'] = time.time() + float(q.get('sec') or 30)
        if q.get('act') == 'mute':
            muted[(room.code, pid)] = time.time() + float(q.get('sec') or 30)
        self.send_json({'ok': True, 'conns': hit})

    def static(self, path):
        if path == '/':
            path = '/index.html'
        full = os.path.normpath(os.path.join(PUBLIC, path.lstrip('/')))
        if not full.startswith(PUBLIC + os.sep) or not os.path.isfile(full):
            return self.send_bytes(404, b'not found', 'text/plain')
        ext = os.path.splitext(full)[1].lower()
        st = os.stat(full)
        etag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        # 语音、字体不会变，缓存一天；图片缓存十分钟；页面和脚本每次都来问一下有没有变（没变只回 304）
        cache = ('no-cache' if DEV else
                 'public, max-age=86400' if ext in ('.m4a', '.mp3', '.wav', '.woff2') else
                 'public, max-age=600' if ext in ('.svg', '.jpg', '.png', '.webp') else 'no-cache')
        # 前面的代理压缩内容时会把 ETag 改成弱校验（W/"..."），比较时要把这个前缀去掉
        seen = [t.strip()[2:] if t.strip().startswith('W/') else t.strip()
                for t in (self.headers.get('If-None-Match') or '').split(',')]
        if etag in seen:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache)
            self.end_headers()
            return
        with open(full, 'rb') as f:
            body = f.read()
        self.send_bytes(200, body, TYPES.get(ext, 'application/octet-stream'), cache, etag)

    def events(self, q):
        room = rooms.get(q.get('code', ''))
        p = room and room.auth(q.get('pid'), q.get('token'))
        if not p:
            return self.fail('房间不存在或已失效', 404)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-transform')
        self.send_header('X-Accel-Buffering', 'no')       # 让反向代理不要攒着不发
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        self.connection.settimeout(WRITE_TIMEOUT)     # 对面收不动了就别一直等
        c = {'pid': p['id'], 'q': queue.Queue(), 'last': None, 'hb': q.get('hb') == '1'}
        conns[room.code].append(c)
        room.attach(p['id'], hb=c['hb'])              # 这里会把当前画面推给刚连上的这条连接
        try:
            # 开头垫一段空白：有些代理和内置浏览器要攒够一定字节才肯往下传
            self.wfile.write(b'retry: 1500\n:' + b' ' * 2048 + b'\n\n')
            self.wfile.flush()
            next_ping, n = time.time() + PING_EVERY, 0
            while not c.get('drop'):
                try:
                    msg = c['q'].get(timeout=max(0.05, min(1.0, next_ping - time.time())))
                except queue.Empty:
                    msg = None
                stalled = max(c.get('stall', 0), muted.get((room.code, c['pid']), 0)) > time.time()
                if msg is not None and not stalled:
                    self.wfile.write(b'data: ' + msg.encode('utf-8') + b'\n\n')
                    self.wfile.flush()
                if time.time() >= next_ping:
                    # 心跳是一条真正的事件（不是注释），手机端收得到，用它判断连接是不是还通
                    next_ping, n = time.time() + PING_EVERY, n + 1
                    if not stalled:
                        self.wfile.write(('event: ping\ndata: %d\n\n' % n).encode('ascii'))
                        self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            try:
                conns[room.code].remove(c)
            except (KeyError, ValueError):
                pass
            room.detach(p['id'], hb=c['hb'])

    # -------------------------------------------------------------- POST

    def do_POST(self):
        try:
            self.post()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout):
            pass
        except Exception:
            oops()
            try:
                self.fail('服务器出错了，请再试一次', 500)
            except OSError:
                pass

    def post(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > 65536 or length < 0:
                self.close_connection = True                # 请求体没读，这条连接不能再用，否则剩下的字节会被当成下一个请求
                return self.fail('请求太大', 413)
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            self.close_connection = True
            return self.fail('请求格式不对')
        path = urlparse(self.path).path
        try:
            if path == '/api/create':
                if too_many('create', self.addr(), CREATE_LIMIT):
                    return self.fail('建房间太频繁了，请稍后再试', 429)
                room = new_room()
                p = room.add_player(body.get('name'))
                if isinstance(body.get('roles'), dict):
                    room.action(p['id'], 'config', {'roles': full_roles(body['roles'])})
                return self.send_json(self.cred(room, p))

            room = rooms.get(str(body.get('code', '')))
            if not room:
                return self.fail('房间不存在，请确认房间号', 404)

            if path == '/api/join':
                # 在锁里只把要回的内容算好，发出去放到锁外面：对面不收数据时，不能连累整个房间都卡住
                with room.lock:
                    p = room.auth(body.get('pid'), body.get('token'))
                    if p:                                   # 老玩家回来了
                        out = self.cred(room, p)
                    elif room.phase == 'lobby':
                        out = self.cred(room, room.add_player(body.get('name')))
                    else:                                   # 游戏已经开始：只能申请认领掉线的座位
                        out = {'claim': room.offline_seats(), 'code': room.code}
                return self.send_json(out)

            if path == '/api/claim':
                # 第一次：提交申请，等房主同意；之后带着申请编号来问结果，同意了就拿到这个座位的身份
                if body.get('rid'):
                    if body.get('cancel'):                  # 撤回；要是房主已经同意了，就照样把身份交给他
                        state, p = room.cancel_claim(body.get('rid'))
                    else:
                        state, p = room.claim_status(body.get('rid'))
                    if state == 'ok' and p:
                        return self.send_json(self.cred(room, p))
                    return self.send_json({'rid': body.get('rid'), 'state': state})
                if too_many('claim', self.addr(), CLAIM_LIMIT):
                    return self.fail('申请太频繁了，请稍后再试', 429)
                rid = room.request_claim(body.get('seat'), body.get('name'))
                return self.send_json({'rid': rid, 'state': 'wait'})

            if path in ('/api/act', '/api/beat'):
                p = room.auth(body.get('pid'), body.get('token'))
                if not p:
                    return self.fail('身份已失效，请重新进入房间', 403)
                if path == '/api/beat':                     # 手机回应心跳：我还醒着
                    room.touch(p['id'])
                    if DEV and isinstance(body.get('d'), dict):
                        diags[(room.code, p['id'])] = dict(list(body['d'].items())[:12], at=round(time.time(), 1))
                else:
                    room.action(p['id'], body.get('type'), body.get('data'))
                return self.send_json({'ok': True})
        except GameError as e:
            return self.fail(str(e))
        self.fail('没有这个接口', 404)

    @staticmethod
    def cred(room, p):
        return {'code': room.code, 'pid': p['id'], 'token': p['token'], 'name': p['name']}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def handle_error(self, request, client_address):
        # 手机中途断开（锁屏、关页面、换网络）是家常便饭，不值得在日志里打一大段报错
        if isinstance(sys.exc_info()[1], (ConnectionError, socket.timeout, TimeoutError)):
            return
        ThreadingHTTPServer.handle_error(self, request, client_address)


def start(port=None):
    """启动服务器和后台检查线程，返回服务器对象（测试里也用它）。"""
    try:                                    # 每台手机要占好几个连接；macOS 默认只给 256 个文件句柄，不够
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = 8192 if hard == resource.RLIM_INFINITY else min(8192, hard)
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except (ImportError, ValueError, OSError):
        pass
    if flag('LRS_FAST'):                    # 仅供压力测试：把夜里的停顿和「假装操作」缩短到十分之一
        game.PAUSE_AFTER_NIGHT_FALL, game.PAUSE_BETWEEN_ROLES = 0.3, 0.2
        game.FAKE_ACT = {k: (lo / 10, hi / 10) for k, (lo, hi) in game.FAKE_ACT.items()}
        game.FAKE_DEFAULT = (0.6, 1.1)
    srv = Server(('0.0.0.0', PORT if port is None else port), Handler)
    t = threading.Thread(target=sweeper)
    t.daemon = True
    t.start()
    return srv


def main():
    srv = start()
    print('狼人杀面杀助手已启动')
    print('  本机打开:  http://localhost:%d' % PORT)
    lan = lan_url()
    if lan:
        print('  手机打开:  %s   （手机要和这台电脑连同一个 Wi-Fi）' % lan)
    print('按 Ctrl+C 停止')
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
