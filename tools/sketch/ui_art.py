# -*- coding: utf-8 -*-
"""界面素材：边框、座位牌、选中圈、记号、月亮、药瓶、警徽、卡背。

和头像用同一支笔（rough.Pen），线条是手画的，但尽量少：一圈线、一块平涂，不加排线和装饰。
build() 返回 [(文件名, svg)]。
"""
from rough import Pen, INK, PAPER, BONE, oval, arc, star

RED = '#8f3226'
GOLD = '#c2983c'
BROWN = '#5b4532'
CHALK = '#cfc4a6'           # 深色背景上的线


def side(a, b, n=3):
    return [(a[0] + (b[0] - a[0]) * i / float(n), a[1] + (b[1] - a[1]) * i / float(n)) for i in range(n)]


def frame(name, fill, line, dashed=False, lw=3.6, size=120, inset=7.0):
    """九宫格边框（border-image 用）：一块边缘略微不齐的平涂，外面描一圈线。"""
    p = Pen(name, size, size)
    a, b = inset, size - inset
    c = [(a, a), (b, a), (b, b), (a, b)]
    pts = side(c[0], c[1]) + side(c[1], c[2]) + side(c[2], c[3]) + side(c[3], c[0])
    if fill:
        p.fill(pts, fill, smooth=False, jit=1.0, shift=0)
    if dashed:
        for i in range(4):
            s, e = c[i], c[(i + 1) % 4]
            for k in range(5):
                t0, t1 = k / 5.0 + .03, k / 5.0 + .15
                p.line(s[0] + (e[0] - s[0]) * t0, s[1] + (e[1] - s[1]) * t0, s[0] + (e[0] - s[0]) * t1,
                       s[1] + (e[1] - s[1]) * t1, w=lw, color=line, passes=1)
    elif line:
        p.stroke(pts, closed=True, w=lw, color=line, smooth=False, jit=1.0, passes=1)
    return p.svg()


def token(name, fill, line=INK, dashed=False):
    """座位牌：一个圆。"""
    p = Pen(name, 100, 100)
    if dashed:
        for k in range(9):
            p.stroke(arc(50, 50, 44, 44, k * 40 + 4, k * 40 + 26, n=3), w=3.0, color=line, passes=1)
        return p.svg()
    p.fill(oval(50, 50, 45, 45, n=14), fill, jit=.8, shift=0)
    p.stroke(oval(50, 50, 45, 45, n=14), closed=True, w=3.4, color=line, jit=.8, passes=1)
    return p.svg()


def ring(name, color):
    """选中时圈在座位牌外面的一圈线。"""
    p = Pen(name, 120, 120)
    p.stroke(arc(60, 60, 54, 53, -40, 340, n=14), w=4.0, color=color, jit=1.4, passes=1)
    return p.svg()


def cross(name):
    p = Pen(name, 100, 100)
    for a, b in (((18, 20), (82, 80)), ((80, 18), (20, 84))):
        p.stroke([a, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), b], w=6.0, color=RED, jit=1.6, passes=1)
    return p.svg()


def mark(name, done):
    """座位旁边的小记号：做完了是一个勾，没做完是三个点。"""
    p = Pen(name, 60, 60)
    if done:
        p.shape(oval(30, 30, 25, 25, n=10), '#77834f', w=3.4, passes=1)
        p.stroke([(16, 31), (26, 42), (45, 18)], smooth=False, w=6.5, color=BONE, jit=.8, passes=1)
    else:
        p.shape(oval(30, 30, 25, 25, n=10), BONE, w=3.4, passes=1)
        for x in (18, 30, 42):
            p.dot(x, 31, 3.6)
    return p.svg()


def moon():
    p = Pen('moon', 120, 120)
    cres = arc(60, 60, 48, 48, 50, 310, n=12) + list(reversed(arc(82, 56, 40, 40, 82, 278, n=10)))
    p.shape(cres, '#e6d9a8', w=3.0, passes=1)
    return p.svg()


def potion(name, liquid, cross_label):
    p = Pen(name, 120, 120)
    p.shape([(51, 14), (69, 14), (68, 44), (52, 44)], BONE, smooth=False, w=2.6, passes=1)
    p.shape([(49, 8), (71, 8), (70, 18), (50, 18)], BROWN, smooth=False, w=2.4, passes=1)
    body = oval(60, 76, 34, 32, n=12)
    p.shape(body, BONE, w=3.0, passes=1)
    liq = arc(60, 76, 30, 28, 8, 172, n=8) + [(34, 74), (48, 70), (60, 75), (72, 70), (86, 74)]
    p.shape(liq, liquid, w=2.0, passes=1)
    if cross_label:
        p.line(60, 82, 60, 98, w=4.0, color=BONE, passes=1)
        p.line(52, 90, 68, 90, w=4.0, color=BONE, passes=1)
    else:
        for a, b in (((52, 82), (68, 98)), ((68, 82), (52, 98))):
            p.line(a[0], a[1], b[0], b[1], w=4.0, color=BONE, passes=1)
    return p.svg()


def badge():
    p = Pen('badge', 100, 100)
    p.shape(star(50, 52, 44, 21, 6), GOLD, smooth=False, w=3.6, passes=1)
    p.shape(oval(50, 52, 11, 11, n=8), '#d9b24a', w=2.4, passes=1)
    return p.svg()


def cardback():
    p = Pen('cardback', 200, 280)
    p.fill([(-4, -4), (204, -4), (204, 284), (-4, 284)], '#2b241d', smooth=False, jit=0, shift=0)
    c = [(14, 14), (186, 14), (186, 266), (14, 266)]
    p.stroke(side(c[0], c[1]) + side(c[1], c[2]) + side(c[2], c[3]) + side(c[3], c[0]), closed=True, w=3.0, color=CHALK,
             smooth=False, jit=1.2, passes=1)
    eye = [(52, 140), (76, 118), (100, 110), (124, 118), (148, 140), (124, 162), (100, 170), (76, 162)]
    p.shape(eye, BONE, w=3.0, passes=1)
    p.shape(oval(100, 140, 19, 23, n=10), GOLD, w=2.6, passes=1)
    p.shape([(100, 120), (106, 140), (100, 160), (94, 140)], INK, w=1.6, passes=1)
    return p.svg()


def line():
    p = Pen('line', 300, 10)
    p.stroke([(4, 5), (80, 4), (160, 6), (230, 4.5), (296, 5.5)], w=2.0, jit=.8, passes=1)
    return p.svg(' preserveAspectRatio="none"')


def build():
    return [
        ('frame_paper', frame('f-paper', PAPER, INK)),
        ('frame_bone', frame('f-bone', BONE, INK)),
        ('frame_dark', frame('f-dark', '#1b1612', '#8f8468')),
        ('frame_gold', frame('f-gold', GOLD, INK)),
        ('frame_red', frame('f-red', RED, INK)),
        ('frame_line', frame('f-line', None, CHALK)),
        ('frame_line_ink', frame('f-line-ink', None, INK)),
        ('frame_dash', frame('f-dash', None, CHALK, dashed=True)),
        ('frame_dash_ink', frame('f-dash-ink', None, INK, dashed=True)),
        ('token', token('t', PAPER)),
        ('token_red', token('t-red', '#d9b0a0', line=RED)),
        ('token_dim', token('t-dim', '#8c8068')),
        ('token_empty', token('t-empty', None, line=CHALK, dashed=True)),
        ('token_empty_ink', token('t-empty-ink', None, line=INK, dashed=True)),
        ('ring_red', ring('r-red', '#b5463a')),
        ('ring_gold', ring('r-gold', '#d9b24a')),
        ('cross', cross('x')),
        ('mark_done', mark('m-done', True)), ('mark_wait', mark('m-wait', False)),
        ('moon', moon()),
        ('potion_save', potion('p-save', '#86a54c', True)),
        ('potion_poison', potion('p-poison', '#5d4a66', False)),
        ('badge_sheriff', badge()), ('cardback', cardback()), ('line', line()),
    ]
