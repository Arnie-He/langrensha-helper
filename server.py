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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import qr
from game import GameError, PRESETS, ROLES, ROLE_ORDER, Room, clean_name, full_roles

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, 'public')
PORT = int(os.environ.get('PORT', '3210'))
DEV = bool(os.environ.get('LRS_DEV'))      # 开发时设 LRS_DEV=1：图片不缓存，改完马上能看到
ROOM_TTL = 6 * 3600          # 房间 6 小时没人动就清掉
PING_EVERY = 8               # 每 8 秒给每台手机发一次心跳，用来发现掉线

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
        view = room.view(c['pid'])
        if view is None:
            continue
        msg = json.dumps(view, ensure_ascii=False, separators=(',', ':'))
        if msg != c['last']:
            c['last'] = msg
            c['q'].put(msg)


def new_room():
    with rooms_lock:
        now = time.time()
        for code in [k for k, r in rooms.items()
                     if now - r.touched > ROOM_TTL and not conns.get(k)]:
            del rooms[code]
            conns.pop(code, None)
        while True:
            code = '%04d' % random.SystemRandom().randrange(10000)
            if code not in rooms:
                break
        room = Room(code, on_change=broadcast,
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

    # -------------------------------------------------------------- GET

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == '/api/events':
            return self.events(q)
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
        c = {'pid': p['id'], 'q': queue.Queue(), 'last': None}
        conns[room.code].append(c)
        room.attach(p['id'])
        try:
            self.wfile.write(b'retry: 1500\n\n')
            while True:
                try:
                    msg = c['q'].get(timeout=PING_EVERY)
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
                    continue
                self.wfile.write(b'data: ' + msg.encode('utf-8') + b'\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            try:
                conns[room.code].remove(c)
            except (KeyError, ValueError):
                pass
            room.detach(p['id'])

    # -------------------------------------------------------------- POST

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > 65536:
                return self.fail('请求太大', 413)
            body = json.loads(self.rfile.read(length).decode('utf-8') or '{}')
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return self.fail('请求格式不对')
        path = urlparse(self.path).path
        try:
            if path == '/api/create':
                room = new_room()
                p = room.add_player(body.get('name'))
                if isinstance(body.get('roles'), dict):
                    room.action(p['id'], 'config', {'roles': full_roles(body['roles'])})
                return self.send_json(self.cred(room, p))

            room = rooms.get(str(body.get('code', '')))
            if not room:
                return self.fail('房间不存在，请确认房间号', 404)

            if path == '/api/join':
                with room.lock:
                    p = room.auth(body.get('pid'), body.get('token'))
                    if p:                                   # 老玩家回来了
                        return self.send_json(self.cred(room, p))
                    if room.phase == 'lobby':
                        p = room.add_player(body.get('name'))
                        return self.send_json(self.cred(room, p))
                    # 游戏已经开始：只能认领掉线的座位
                    return self.send_json({'claim': room.offline_seats(), 'code': room.code})

            if path == '/api/claim':
                p = room.claim(body.get('seat'), body.get('name'))
                return self.send_json(self.cred(room, p))

            if path == '/api/act':
                p = room.auth(body.get('pid'), body.get('token'))
                if not p:
                    return self.fail('身份已失效，请重新进入房间', 403)
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


def main():
    srv = Server(('0.0.0.0', PORT), Handler)
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
