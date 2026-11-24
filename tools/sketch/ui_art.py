# -*- coding: utf-8 -*-
"""界面素材：纸片边框、座位牌、月亮太阳、药瓶、徽记、卡背、圆桌钟面、远景剪影。

和头像用同一支笔（rough.Pen），所以线条和颜色是一套。build() 返回 [(文件名, svg)]。
"""
import math

from rough import Pen, INK, PAPER, BONE, mir, oval, arc, star

DARK = '#2b241d'
NIGHT = '#221c16'
RED = '#8f3226'
GOLD = '#c2983c'
GREEN = '#6c7a48'
STEEL = '#8d9596'
BROWN = '#5b4532'
STRETCH = ' preserveAspectRatio="none"'


def side(a, b, n=3):
    return [(a[0] + (b[0] - a[0]) * i / float(n), a[1] + (b[1] - a[1]) * i / float(n)) for i in range(n)]


def frame(name, fill, line, lw=4.6, dashed=False, double=False, size=120, edge=4.0, inset=14.0):
    """九宫格边框（border-image 用）：一张边缘不齐的纸片，离边一点画一圈墨线，转角处出头。

    纸边在 edge，墨线在 inset；这样纸片放在深色背景上，墨线也看得见。
    """
    p = Pen(name, size, size)
    if fill:
        a, b = edge, size - edge
        c = [(a, a), (b, a), (b, b), (a, b)]
        p.fill(side(c[0], c[1], 4) + side(c[1], c[2], 4) + side(c[2], c[3], 4) + side(c[3], c[0], 4), fill, smooth=False,
               jit=1.7, shift=0)
    a, b = inset, size - inset
    c = [(a, a), (b, a), (b, b), (a, b)]
    for i in range(4):
        s, e = c[i], c[(i + 1) % 4]
        if dashed:
            for k in range(5):
                t0, t1 = k / 5.0 + .03, k / 5.0 + .15
                p.line(s[0] + (e[0] - s[0]) * t0, s[1] + (e[1] - s[1]) * t0, s[0] + (e[0] - s[0]) * t1,
                       s[1] + (e[1] - s[1]) * t1, w=lw * .8, color=line, passes=1)
        else:
            p.stroke(side(s, e, 3) + [e], w=lw, color=line, smooth=False, jit=1.2, over=6.0)
            if double:
                k = 7.0
                s2 = (s[0] + (k if s[0] < 60 else -k), s[1] + (k if s[1] < 60 else -k))
                e2 = (e[0] + (k if e[0] < 60 else -k), e[1] + (k if e[1] < 60 else -k))
                p.stroke([s2, e2], w=lw * .35, color=line, smooth=False, jit=1.0, passes=1, op=.8)
    return p.svg()


def token(name, rim, inner, line=INK, dashed=False, shade=True):
    p = Pen(name, 100, 100)
    if dashed:
        for k in range(9):
            p.stroke(arc(50, 50, 43, 43, k * 40 + 4, k * 40 + 26, n=3), w=3.0, color=line, passes=1)
        return p.svg()
    p.shape(oval(50, 50, 45, 45, n=14), rim, w=3.4, color=line)
    p.hatch(oval(58, 58, 40, 40, n=12), angle=-45, gap=4.5, op=.35)
    p.shape(oval(50, 50, 35, 35, n=12), inner, w=2.6, color=line)
    if shade:
        p.hatch([(60, 20), (84, 44), (78, 70), (56, 84), (70, 56)], angle=-50, gap=4, op=.3)
    for a in range(0, 360, 45):
        q = arc(50, 50, 40, 40, a + 10, a + 10, n=1)[0]
        p.dot(q[0], q[1], 1.5, color=line, op=.8)
    return p.svg()


def ring(name, color):
    """选中时圈在座位牌外面的一圈乱线。"""
    p = Pen(name, 120, 120)
    for k in range(3):
        r = 52 + k * 1.5
        p.stroke(arc(60 + p.j(2), 60 + p.j(2), r, r * p.rnd.uniform(.93, 1.0), 20 * k - 30, 20 * k + 350, n=12),
                 w=3.2 - k * .6, color=color, jit=1.6, passes=1)
    return p.svg()


def cross(name):
    p = Pen(name, 100, 100)
    for a, b in (((16, 18), (84, 82)), ((82, 16), (18, 86))):
        p.stroke([a, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), b], w=6.0, color=RED, jit=2.0, over=4)
    return p.svg()


def moon():
    p = Pen('moon', 120, 120)
    outer = arc(60, 60, 48, 48, 50, 310, n=12)
    innr = list(reversed(arc(82, 56, 40, 40, 82, 278, n=10)))
    cres = outer + innr
    p.shape(cres, '#e6d9a8', w=3.2)
    p.hatch(cres, angle=-40, gap=4.6, op=.32)
    for x, y, r in ((30, 50, 5), (36, 76, 4), (46, 30, 3)):
        p.stroke(oval(x, y, r, r * .8, n=7), closed=True, w=1.4, passes=1, op=.6)
    for x, y in ((96, 30), (104, 70), (84, 96)):
        p.line(x - 4, y, x + 4, y, w=1.5, color=BONE, passes=1)
        p.line(x, y - 4, x, y + 4, w=1.5, color=BONE, passes=1)
    return p.svg()


def sun():
    p = Pen('sun', 120, 120)
    for k in range(10):
        a = math.radians(k * 36 + 8)
        b0 = (60 + 31 * math.cos(a - .2), 60 + 31 * math.sin(a - .2))
        b1 = (60 + 31 * math.cos(a + .2), 60 + 31 * math.sin(a + .2))
        tip = (60 + (48 + (k % 2) * 7) * math.cos(a), 60 + (48 + (k % 2) * 7) * math.sin(a))
        p.shape([b0, tip, b1], GOLD, smooth=False, w=2.2)
    disc = oval(60, 60, 28, 28, n=12)
    p.shape(disc, '#d9b24a', w=3.2)
    p.hatch(oval(66, 66, 20, 20), angle=-45, gap=4.2, op=.32)
    p.stroke(arc(52, 54, 8, 5, 200, 340, n=4), w=2.0)
    p.stroke(arc(70, 54, 8, 5, 200, 340, n=4), w=2.0)
    p.stroke(arc(60, 74, 9, 5, 200, 340, n=4), w=2.0)
    return p.svg()


def potion(name, liquid, label):
    p = Pen(name, 120, 120)
    p.shape([(50, 12), (70, 12), (69, 24), (51, 24)], BROWN, smooth=False, w=2.4)
    p.shape([(52, 24), (68, 24), (68, 46), (52, 46)], BONE, smooth=False, w=2.4)
    if label == 'cross':
        body = oval(60, 76, 34, 32, n=12)
    else:
        body = [(60, 42), (86, 60), (92, 96), (76, 110), (44, 110), (28, 96), (34, 60)]
    p.shape(body, BONE, w=3.2, smooth=(label == 'cross'))
    if label == 'cross':
        liq = arc(60, 76, 30, 28, 10, 170, n=8) + [(34, 72), (48, 68), (60, 73), (72, 68), (86, 72)]
    else:
        liq = [(33, 72), (48, 68), (60, 73), (74, 68), (88, 72), (90, 96), (75, 107), (45, 107), (30, 96)]
    p.shape(liq, liquid, w=2.0, smooth=(label == 'cross'))
    p.hatch(liq, angle=-45, gap=4.2, op=.35, smooth=(label == 'cross'))
    tag = [(46, 78), (74, 78), (74, 100), (46, 100)]
    p.shape(tag, BONE, smooth=False, w=2.0)
    if label == 'cross':
        p.line(60, 82, 60, 96, w=3.2, color=RED)
        p.line(53, 89, 67, 89, w=3.2, color=RED)
    else:
        p.shape(oval(60, 86, 7, 6, n=8), BONE, w=1.8)
        p.dot(57, 86, 1.6)
        p.dot(63, 86, 1.6)
        p.line(56, 95, 64, 95, w=1.6, passes=1)
        for x in (58, 60, 62):
            p.line(x, 93, x, 97, w=1.0, passes=1)
    for x, y, r in ((84, 36, 4), (94, 22, 3), (80, 16, 2)):
        p.stroke(oval(x, y, r, r, n=6), closed=True, w=1.4, passes=1, op=.8, color=BONE)
    return p.svg()


def emblem_good():
    p = Pen('emblem-good', 120, 120)
    sh = [(60, 8), (100, 22), (98, 66), (60, 112), (22, 66), (20, 22)]
    p.shape(sh, '#77834f', w=3.6)
    p.hatch([(64, 12), (100, 24), (98, 66), (64, 106)], angle=-50, gap=4.6, op=.35, smooth=False)
    p.stroke([(60, 18), (90, 28), (88, 62), (60, 98), (32, 62), (30, 28)], closed=True, w=1.4, passes=1, op=.6, color=BONE)
    p.shape([(52, 56), (68, 56), (67, 88), (53, 88)], BONE, smooth=False, w=2.4)
    fl = [(60, 56), (50, 44), (60, 24), (70, 44)]
    p.shape(fl, GOLD, w=2.4)
    p.line(60, 56, 60, 48, w=1.6, passes=1)
    for a in range(200, 341, 35):
        q = arc(60, 40, 22, 22, a, a, n=1)[0]
        p.line(q[0], q[1], q[0] + (q[0] - 60) * .3, q[1] + (q[1] - 40) * .3, w=1.3, passes=1, color=BONE, op=.8)
    return p.svg()


def emblem_wolf():
    p = Pen('emblem-wolf', 120, 120)
    disc = oval(60, 60, 50, 50, n=14)
    p.shape(disc, '#3a2a26', w=3.6)
    p.hatch(disc, angle=-45, gap=5, op=.4, color=BONE)
    for k, x in enumerate((38, 58, 78)):
        cl = [(x + 12, 20 + k * 2), (x + 4, 46), (x - 2, 76), (x - 10, 100 - k * 3), (x + 2, 78), (x + 10, 48)]
        p.shape(cl, RED, w=2.2)
    return p.svg()


def badge():
    p = Pen('badge', 100, 100)
    st = star(50, 52, 44, 21, 6)
    p.shape(st, GOLD, smooth=False, w=3.6)
    p.hatch([(50, 52)] + st[0:5], angle=-45, gap=4, op=.35, smooth=False)
    for i in range(0, 12, 2):
        p.dot(50 + (st[i][0] - 50) * .82, 52 + (st[i][1] - 52) * .82, 2.2)
    p.shape(oval(50, 52, 13, 13, n=9), '#d9b24a', w=2.6)
    p.stroke(star(50, 52, 8, 3.5, 5), closed=True, smooth=False, w=1.6, passes=1)
    return p.svg()


def cardback():
    p = Pen('cardback', 200, 280)
    p.fill([(-4, -4), (204, -4), (204, 284), (-4, 284)], '#3b3128', smooth=False, jit=0, shift=0)
    p.hatch([(0, 0), (200, 0), (200, 280), (0, 280)], angle=38, gap=7, op=.22, color=BONE, smooth=False, cross=True)
    for ins, w in ((10, 3.4), (18, 1.4)):
        c = [(ins, ins), (200 - ins, ins), (200 - ins, 280 - ins), (ins, 280 - ins)]
        for i in range(4):
            p.stroke(side(c[i], c[(i + 1) % 4], 3) + [c[(i + 1) % 4]], w=w, color=BONE, smooth=False, jit=1.2, over=4)
    dia = [(100, 56), (164, 140), (100, 224), (36, 140)]
    p.shape(dia, '#2b241d', smooth=False, w=3.0, color=BONE)
    for a in range(0, 360, 20):
        q0 = arc(100, 140, 52, 52, a, a, n=1)[0]
        q1 = arc(100, 140, 68 + (a % 40) * .3, 68 + (a % 40) * .3, a, a, n=1)[0]
        p.line(q0[0], q0[1], q1[0], q1[1], w=1.4, color=GOLD, passes=1, op=.8)
    eye = [(56, 140), (78, 118), (100, 110), (122, 118), (144, 140), (122, 162), (100, 170), (78, 162)]
    p.shape(eye, BONE, w=3.0)
    p.shape(oval(100, 140, 19, 23, n=10), GOLD, w=2.6)
    p.shape([(100, 120), (106, 140), (100, 160), (94, 140)], INK, w=1.6)
    p.hatch(eye, angle=-50, gap=5, op=.25)
    for cx, cy, sx, sy in ((30, 30, 1, 1), (170, 30, -1, 1), (30, 250, 1, -1), (170, 250, -1, -1)):
        p.stroke([(cx, cy + sy * 16), (cx, cy), (cx + sx * 16, cy), (cx + sx * 10, cy + sy * 8), (cx + sx * 4, cy + sy * 6)],
                 w=2.0, color=GOLD, passes=1)
    for k, x in enumerate((84, 100, 116)):
        p.stroke([(x + 5, 236), (x, 250), (x - 4, 262)], w=3.0 - abs(k - 1) * .6, color=RED)
        p.stroke([(x - 5, 44), (x, 30), (x + 4, 18)], w=3.0 - abs(k - 1) * .6, color=RED)
    return p.svg()


def clock():
    """圆桌：外圈一格一格是白天（黄）、黄昏（红）、夜晚（蓝），中间一张纸写字。"""
    p = Pen('clock', 200, 200)
    p.shape(oval(100, 100, 97, 97, n=16), '#4a3b2a', w=3.6)
    cols = ['#c9a13a'] * 8 + ['#a5543a'] * 3 + ['#3d4c5e'] * 5
    for i, c in enumerate(cols):
        a0, a1 = -90 + i * 22.5 + 2, -90 + (i + 1) * 22.5 - 2
        wedge = arc(100, 100, 90, 90, a0, a1, n=3) + list(reversed(arc(100, 100, 64, 64, a0, a1, n=3)))
        p.shape(wedge, c, smooth=False, w=2.0, jit=.8)
        p.hatch(wedge, angle=a0 + 60, gap=4.4, op=.25, smooth=False)
    p.shape(oval(100, 100, 58, 58, n=14), PAPER, w=3.2)
    p.hatch([(118, 50), (152, 84), (150, 120), (120, 152), (136, 104)], angle=-50, gap=4.6, op=.28)
    return p.svg()


def hand():
    p = Pen('hand', 200, 200)
    p.shape([(100, 2), (112, 30), (100, 44), (88, 30)], BONE, smooth=False, w=3.0)
    p.line(100, 12, 100, 36, w=1.4, passes=1)
    return p.svg()


def tree(p, x, y, h, lean=0.0, depth=3, w=5.0):
    """一棵干瘦的枯树：主干分叉，枝头带钩。"""
    if depth == 0 or h < 8:
        p.stroke([(x, y), (x + lean * h * .5 + p.j(3), y - h * .6), (x + lean * h + p.j(4), y - h)], w=max(1.0, w), passes=1)
        return
    tx, ty = x + lean * h * .6 + p.j(4), y - h * .6
    p.stroke([(x, y), ((x + tx) / 2.0 + p.j(3), (y + ty) / 2.0), (tx, ty)], w=w, passes=2)
    for s in (-1, 1):
        tree(p, tx, ty, h * p.rnd.uniform(.5, .68), lean + s * p.rnd.uniform(.25, .6), depth - 1, w * .6)


def house(p, x, y, w, h, tilt=0.0, lit=True):
    t = tilt * h
    body = [(x, y), (x + t, y - h), (x + w + t, y - h), (x + w, y)]
    roof = [(x + t - 6, y - h), (x + t + w * .5 + tilt * 30, y - h - w * .9), (x + t + w + 6, y - h)]
    p.shape(body, DARK, smooth=False, w=2.6)
    p.shape(roof, '#1c1712', smooth=False, w=2.6)
    p.hatch(roof, angle=60, gap=5, op=.5, color=BONE, smooth=False)
    ch = x + t + w * .72
    p.shape([(ch, y - h - w * .5), (ch + 2, y - h - w * .95), (ch + 9, y - h - w * .92), (ch + 8, y - h - w * .3)],
            DARK, smooth=False, w=2.0)
    if lit:
        wx, wy = x + t * .5 + w * .28, y - h * .62
        p.shape([(wx, wy), (wx + w * .3, wy - 1), (wx + w * .3, wy + h * .3), (wx, wy + h * .3)], GOLD, smooth=False, w=2.0)
        p.line(wx + w * .15, wy, wx + w * .15, wy + h * .3, w=1.2, passes=1)
        p.line(wx, wy + h * .15, wx + w * .3, wy + h * .15, w=1.2, passes=1)


def scene():
    """屏幕底部的远景：歪房子、枯树、栅栏、墓碑，全是墨色剪影。"""
    p = Pen('scene', 600, 240)
    hill = [(-10, 250), (-10, 178), (60, 160), (150, 172), (240, 150), (330, 166), (420, 148), (520, 164), (610, 152), (610, 250)]
    tree(p, 40, 170, 100, lean=.08, w=6)
    tree(p, 548, 162, 118, lean=-.1, w=6.5)
    tree(p, 300, 166, 62, lean=.14, w=4)
    house(p, 96, 172, 54, 46, tilt=-.07)
    house(p, 176, 164, 40, 62, tilt=.09, lit=False)
    house(p, 388, 158, 62, 50, tilt=.06)
    house(p, 470, 166, 36, 40, tilt=-.1)
    p.shape(hill, '#1c1712', w=3.0)
    p.hatch(hill, angle=14, gap=9, w=.8, op=.16, color=BONE)
    for x in range(232, 300, 14):
        p.line(x, 168 + p.j(3), x + p.j(2), 144 + p.j(4), w=2.6)
    p.stroke([(226, 152), (262, 156), (298, 150)], w=2.0)
    for x, y in ((340, 170), (360, 176)):
        p.shape([(x, y), (x, y - 20), (x + 6, y - 27), (x + 13, y - 20), (x + 13, y)], '#3a332c', w=2.2)
        p.line(x + 6.5, y - 20, x + 6.5, y - 8, w=1.4, color=BONE, passes=1)
        p.line(x + 3, y - 15, x + 10, y - 15, w=1.4, color=BONE, passes=1)
    return p.svg(' preserveAspectRatio="xMidYMax slice"')


def vignette():
    """屏幕四角的乱线暗角。"""
    p = Pen('vignette', 300, 600)
    for tri, ang in (([(0, 0), (150, 0), (0, 210)], 55), ([(300, 0), (150, 0), (300, 210)], -55),
                     ([(0, 600), (0, 400), (140, 600)], -55), ([(300, 600), (300, 400), (160, 600)], 55)):
        p.hatch(tri, angle=ang, gap=9, w=1.6, op=.5, smooth=False, jit=1.5)
        small = [tri[0], ((tri[0][0] + tri[1][0]) / 2.0, tri[1][1]), (tri[2][0], (tri[0][1] + tri[2][1]) / 2.0)]
        p.hatch(small, angle=ang + 80, gap=8, w=1.5, op=.5, smooth=False, jit=1.5)
    return p.svg(STRETCH)


def line():
    p = Pen('line', 300, 10)
    p.stroke([(4, 5), (80, 4), (160, 6), (230, 4.5), (296, 5.5)], w=2.2, jit=.9)
    return p.svg(STRETCH)


def torn():
    """底部弹层上沿的撕纸边。"""
    p = Pen('torn', 300, 16)
    top = [(0, 9)]
    x = 0.0
    while x < 300:
        x += p.rnd.uniform(5, 13)
        top.append((min(x, 300), p.rnd.uniform(3, 12)))
    p.fill(top + [(300, 20), (0, 20)], PAPER, smooth=False, jit=0, shift=0)
    p.stroke(top, w=1.6, smooth=False, jit=.3, passes=1, op=.8)
    return p.svg(STRETCH)


def claw():
    """标题旁边的三道爪痕。"""
    p = Pen('claw', 120, 120)
    for k, x in enumerate((30, 56, 82)):
        cl = [(x + 22, 8 + k * 3), (x + 10, 40), (x + 2, 78), (x - 8, 112 - k * 4), (x + 6, 80), (x + 16, 42)]
        p.shape(cl, '#b5463a', w=2.0)
    return p.svg()


def build():
    out = [
        ('frame_paper', frame('f-paper', PAPER, INK)),
        ('frame_dark', frame('f-dark', NIGHT, '#a39675', lw=3.6)),
        ('frame_gold', frame('f-gold', GOLD, INK)),
        ('frame_red', frame('f-red', RED, INK)),
        ('frame_wood', frame('f-wood', '#4a3b2a', '#c9bb97', lw=3.4)),
        ('frame_ghost', frame('f-ghost', None, '#b9ab8a', dashed=True, inset=9.0, lw=5.0)),
        ('frame_ghost_ink', frame('f-ghost-ink', None, INK, dashed=True, inset=9.0, lw=5.0)),
        ('frame_card', frame('f-card', BONE, INK, double=True, inset=12.0)),
        ('stamp_red', frame('s-red', None, RED, lw=6.0, double=True, inset=9.0)),
        ('stamp_green', frame('s-green', None, '#4f5f33', lw=6.0, double=True, inset=9.0)),
        ('token', token('t', '#a9853a', PAPER)),
        ('token_red', token('t-red', RED, '#d9b9a0')),
        ('token_dim', token('t-dim', '#5b4a30', '#8c8068')),
        ('token_empty', token('t-empty', None, None, line='#b9ab8a', dashed=True)),
        ('token_empty_ink', token('t-empty-ink', None, None, line=INK, dashed=True)),
        ('ring_red', ring('r-red', RED)),
        ('ring_gold', ring('r-gold', '#d9b24a')),
        ('cross', cross('x')),
        ('moon', moon()), ('sun', sun()),
        ('potion_save', potion('p-save', '#86a54c', 'cross')),
        ('potion_poison', potion('p-poison', '#5d4a66', 'skull')),
        ('emblem_good', emblem_good()), ('emblem_wolf', emblem_wolf()),
        ('badge_sheriff', badge()), ('cardback', cardback()),
        ('clock', clock()), ('hand', hand()),
        ('scene', scene()), ('vignette', vignette()), ('line', line()), ('torn', torn()), ('claw', claw()),
    ]
    return out
