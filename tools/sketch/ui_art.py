# -*- coding: utf-8 -*-
"""界面素材：边框、座位牌、选中圈、记号、月亮、药瓶、徽记、卡背、圆桌刻度、远景剪影。

和头像用同一支笔（rough.Pen）。装饰的分寸：线条来回描两遍、转角出头，色块平涂，
暗部只带一点排线；不用纸纹、阴影和整面的乱线。
build() 返回 [(文件名, svg)]。
"""
from rough import Pen, INK, PAPER, BONE, oval, arc, star

RED = '#8f3226'
GOLD = '#c2983c'
BROWN = '#5b4532'
CHALK = '#cfc4a6'           # 深色背景上的线
STRETCH = ' preserveAspectRatio="none"'


def side(a, b, n=3):
    return [(a[0] + (b[0] - a[0]) * i / float(n), a[1] + (b[1] - a[1]) * i / float(n)) for i in range(n)]


def frame(name, fill, line, dashed=False, lw=3.4, size=120, edge=5.0, inset=10.0):
    """九宫格边框（border-image 用）：一块边缘略微不齐的平涂，靠里一点描一圈线。

    每条边单独画、描两遍，两头出头一点，所以转角是交叉的，像手画的方框。
    """
    p = Pen(name, size, size)
    if fill:
        a, b = edge, size - edge
        c = [(a, a), (b, a), (b, b), (a, b)]
        p.fill(side(c[0], c[1]) + side(c[1], c[2]) + side(c[2], c[3]) + side(c[3], c[0]), fill, smooth=False, jit=1.2, shift=0)
    a, b = inset, size - inset
    c = [(a, a), (b, a), (b, b), (a, b)]
    for i in range(4):
        s, e = c[i], c[(i + 1) % 4]
        if dashed:
            for k in range(5):
                t0, t1 = k / 5.0 + .03, k / 5.0 + .15
                p.line(s[0] + (e[0] - s[0]) * t0, s[1] + (e[1] - s[1]) * t0, s[0] + (e[0] - s[0]) * t1,
                       s[1] + (e[1] - s[1]) * t1, w=lw, color=line, passes=1)
        elif line:
            p.stroke(side(s, e) + [e], w=lw, color=line, smooth=False, jit=1.0, over=5.0)
    return p.svg()


def token(name, rim, inner, line=INK, dashed=False):
    """座位牌：一圈边，中间一块圆纸，右下带几笔排线。"""
    p = Pen(name, 100, 100)
    if dashed:
        for k in range(9):
            p.stroke(arc(50, 50, 44, 44, k * 40 + 4, k * 40 + 26, n=3), w=3.0, color=line, passes=1)
        return p.svg()
    p.shape(oval(50, 50, 45, 45, n=14), rim, w=3.2, color=line, jit=.8, shift=0)
    p.shape(oval(50, 50, 37, 37, n=12), inner, w=1.8, color=line, jit=.7, passes=1, shift=0)
    p.hatch(arc(50, 50, 35, 35, -20, 80, n=6) + list(reversed(arc(44, 44, 31, 31, -8, 68, n=6))), angle=-48, gap=4.4, op=.3,
            smooth=False)
    return p.svg()


def ring(name, color):
    """选中时圈在座位牌外面的线：随手绕了两圈。"""
    p = Pen(name, 120, 120)
    for k in range(2):
        r = 53 + k * 1.8
        p.stroke(arc(60 + p.j(1.5), 60 + p.j(1.5), r, r * p.rnd.uniform(.95, 1.0), 30 * k - 40, 30 * k + 345, n=13),
                 w=3.6 - k * 1.4, color=color, jit=1.4, passes=1)
    return p.svg()


def cross(name):
    p = Pen(name, 100, 100)
    for a, b in (((18, 20), (82, 80)), ((80, 18), (20, 84))):
        p.stroke([a, ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), b], w=6.0, color=RED, jit=1.8, over=4)
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
    p.shape(cres, '#e6d9a8', w=3.0)
    p.hatch(cres, angle=-40, gap=5.6, op=.24)
    for x, y, r in ((30, 50, 5), (36, 77, 4), (47, 30, 3)):
        p.stroke(oval(x, y, r, r * .8, n=7), closed=True, w=1.4, passes=1, op=.5)
    return p.svg()


def stars():
    """深色天空上的几颗星：只画在两侧和最上面，中间留给标题和月亮。"""
    p = Pen('stars', 400, 240)
    spots = [(30, 36), (96, 62), (62, 120), (22, 190), (54, 232), (140, 14), (268, 20), (304, 54), (376, 122), (332, 196),
             (372, 230)]
    for i, (x, y) in enumerate(spots):
        x, y, r = x + p.j(4), y + p.j(4), p.rnd.uniform(2.6, 4.6)
        if i % 3 != 2:
            p.line(x - r, y, x + r, y, w=1.3, color=BONE, jit=.3, passes=1, op=.8)
            p.line(x, y - r * 1.2, x, y + r * 1.2, w=1.3, color=BONE, jit=.3, passes=1, op=.8)
        else:
            p.dot(x, y, r * .42, color=BONE, op=.75)
    return p.svg()


def potion(name, liquid, label):
    p = Pen(name, 120, 120)
    p.shape([(50, 12), (70, 12), (69, 24), (51, 24)], BROWN, smooth=False, w=2.4)
    p.shape([(52, 24), (68, 24), (68, 46), (52, 46)], BONE, smooth=False, w=2.4)
    rnd = label == 'cross'
    if rnd:
        body = oval(60, 76, 34, 32, n=12)
        liq = arc(60, 76, 30, 28, 10, 170, n=8) + [(34, 72), (48, 68), (60, 73), (72, 68), (86, 72)]
    else:
        body = [(60, 42), (86, 60), (92, 96), (76, 110), (44, 110), (28, 96), (34, 60)]
        liq = [(33, 72), (48, 68), (60, 73), (74, 68), (88, 72), (90, 96), (75, 107), (45, 107), (30, 96)]
    p.shape(body, BONE, w=3.0, smooth=rnd)
    p.shape(liq, liquid, w=2.0, smooth=rnd, passes=1)
    p.hatch(liq, angle=-45, gap=5.0, op=.28, smooth=rnd)
    if rnd:
        p.line(60, 81, 60, 98, w=4.0, color=BONE, passes=1)
        p.line(51, 90, 69, 90, w=4.0, color=BONE, passes=1)
    else:
        for a, b in (((52, 80), (68, 98)), ((68, 80), (52, 98))):
            p.line(a[0], a[1], b[0], b[1], w=4.0, color=BONE, passes=1)
    for x, y, r in ((85, 36, 4), (95, 22, 3)):
        p.stroke(oval(x, y, r, r, n=6), closed=True, w=1.4, passes=1, op=.8, color=BONE)
    return p.svg()


def emblem_good():
    """好人：一面盾，中间一支点着的蜡烛。"""
    p = Pen('emblem-good', 120, 120)
    sh = [(60, 8), (100, 22), (98, 66), (60, 112), (22, 66), (20, 22)]
    p.shape(sh, '#77834f', w=3.4)
    p.hatch([(64, 12), (100, 24), (98, 66), (64, 106)], angle=-50, gap=5.2, op=.26, smooth=False)
    p.shape([(52, 56), (68, 56), (67, 88), (53, 88)], BONE, smooth=False, w=2.4, passes=1)
    p.shape([(60, 56), (50, 44), (60, 24), (70, 44)], GOLD, w=2.4, passes=1)
    p.line(60, 56, 60, 48, w=1.6, passes=1)
    return p.svg()


def emblem_wolf():
    """狼人：一块深色的圆，上面三道爪痕。"""
    p = Pen('emblem-wolf', 120, 120)
    disc = oval(60, 60, 50, 50, n=14)
    p.shape(disc, '#3a2a26', w=3.4)
    for k, x in enumerate((38, 58, 78)):
        cl = [(x + 12, 20 + k * 2), (x + 4, 46), (x - 2, 76), (x - 10, 100 - k * 3), (x + 2, 78), (x + 10, 48)]
        p.shape(cl, RED, w=2.0, passes=1)
    return p.svg()


def badge():
    p = Pen('badge', 100, 100)
    st = star(50, 52, 44, 21, 6)
    p.shape(st, GOLD, smooth=False, w=3.4)
    p.shape(oval(50, 52, 12, 12, n=9), '#d9b24a', w=2.4, passes=1)
    return p.svg()


def cardback():
    p = Pen('cardback', 200, 280)
    p.fill([(-4, -4), (204, -4), (204, 284), (-4, 284)], '#2b241d', smooth=False, jit=0, shift=0)
    for ins, w in ((11, 3.2), (19, 1.3)):
        c = [(ins, ins), (200 - ins, ins), (200 - ins, 280 - ins), (ins, 280 - ins)]
        for i in range(4):
            p.stroke(side(c[i], c[(i + 1) % 4]) + [c[(i + 1) % 4]], w=w, color=CHALK, smooth=False, jit=1.2, over=4, passes=1)
    for a in range(0, 360, 20):
        q0 = arc(100, 140, 54, 54, a, a, n=1)[0]
        q1 = arc(100, 140, 68 + (a % 40) * .3, 68 + (a % 40) * .3, a, a, n=1)[0]
        p.line(q0[0], q0[1], q1[0], q1[1], w=1.4, color=GOLD, passes=1, op=.75)
    eye = [(52, 140), (76, 118), (100, 110), (124, 118), (148, 140), (124, 162), (100, 170), (76, 162)]
    p.shape(eye, BONE, w=3.0)
    p.shape(oval(100, 140, 19, 23, n=10), GOLD, w=2.6, passes=1)
    p.shape([(100, 120), (106, 140), (100, 160), (94, 140)], INK, w=1.6, passes=1)
    for cx, cy, sx, sy in ((34, 34, 1, 1), (166, 34, -1, 1), (34, 246, 1, -1), (166, 246, -1, -1)):
        p.stroke([(cx, cy + sy * 16), (cx, cy), (cx + sx * 16, cy), (cx + sx * 10, cy + sy * 8), (cx + sx * 4, cy + sy * 6)],
                 w=1.8, color=GOLD, passes=1, op=.85)
    return p.svg()


def dial():
    """圆桌中间的一圈刻度（当蒙版用，颜色由样式决定）。"""
    p = Pen('dial', 200, 200)
    p.stroke(arc(100, 100, 93, 93, -70, 300, n=18), w=2.2, jit=1.2)
    for i in range(24):
        a = i * 15 + p.j(1.5)
        r0 = 80 if i % 6 == 0 else 85
        q0, q1 = arc(100, 100, r0, r0, a, a, n=1)[0], arc(100, 100, 92, 92, a, a, n=1)[0]
        p.stroke([q0, q1], w=2.6 if i % 6 == 0 else 1.5, jit=.5, passes=1)
    return p.svg()


def claw():
    """标题旁边的三道爪痕。"""
    p = Pen('claw', 120, 120)
    for k, x in enumerate((30, 56, 82)):
        cl = [(x + 22, 8 + k * 3), (x + 10, 40), (x + 2, 78), (x - 8, 112 - k * 4), (x + 6, 80), (x + 16, 42)]
        p.shape(cl, '#b5463a', w=1.8, passes=1)
    return p.svg()


def line():
    p = Pen('line', 300, 10)
    p.stroke([(4, 5), (80, 4), (160, 6), (230, 4.5), (296, 5.5)], w=2.0, jit=.8, passes=1)
    return p.svg(STRETCH)


def orn():
    """中间带一个小菱形的分隔线（当蒙版用）。"""
    p = Pen('orn', 300, 16)
    p.stroke([(6, 8), (60, 7.4), (128, 8.6)], w=2.0, jit=.7, passes=1)
    p.stroke([(172, 8.4), (236, 7.2), (294, 8)], w=2.0, jit=.7, passes=1)
    p.stroke([(150, 2), (158, 8), (150, 14), (142, 8)], closed=True, smooth=False, w=1.8, jit=.5, passes=1)
    p.dot(134, 8, 1.3)
    p.dot(166, 8, 1.3)
    return p.svg()


# ---------------------------------------------------------------- 远景

def tree(p, x, y, h, lean=0.0, depth=3, w=4.6):
    """一棵干瘦的枯树：主干分叉，枝头歪着。"""
    if depth == 0 or h < 7:
        p.stroke([(x, y), (x + lean * h * .5 + p.j(2), y - h * .6), (x + lean * h + p.j(3), y - h)], w=max(1.2, w), passes=1)
        return
    tx, ty = x + lean * h * .6 + p.j(3), y - h * .6
    p.stroke([(x, y), ((x + tx) / 2.0 + p.j(2), (y + ty) / 2.0), (tx, ty)], w=w, passes=1)
    for s in (-1, 1):
        tree(p, tx, ty, h * p.rnd.uniform(.5, .66), lean + s * p.rnd.uniform(.3, .6), depth - 1, w * .62)


def house(p, x, y, w, h, tilt=0.0, window=True, steep=.75):
    """一间歪房子的剪影。窗户是镂空的，透出后面天空的颜色。"""
    t = tilt * h
    body = p.wob([(x, y), (x + t, y - h), (x + w + t, y - h), (x + w, y)], .7)
    d = p.d_sharp(body, True)
    if window:
        wx, wy, ww, wh = x + t * .6 + w * .3, y - h * .8, w * .3, h * .36
        d += p.d_sharp(p.wob([(wx, wy), (wx, wy + wh), (wx + ww, wy + wh), (wx + ww, wy)], .4), True)
    p.raw('<path d="%s" fill="%s" fill-rule="evenodd"/>' % (d, INK))
    p.fill([(x + t - 5, y - h + 1), (x + t + w * .5 + tilt * 20, y - h - w * steep), (x + t + w + 5, y - h + 1)], INK,
           smooth=False, jit=.8, shift=0)
    ch = x + t + w * .7
    p.fill([(ch, y - h - w * .1), (ch + 1, y - h - w * steep * .9), (ch + 7, y - h - w * steep * .88), (ch + 7, y - h)], INK,
           smooth=False, jit=.5, shift=0)
    if window:
        p.line(wx + ww / 2.0, wy, wx + ww / 2.0, wy + wh, w=1.3, passes=1, jit=.3)


def skyline():
    """按钮栏上沿的一条远景：歪房子、枯树、小教堂、栅栏、墓碑。

    是一张蒙版（只看形状），颜色由样式里的 --ground 决定；左右两头一样高，可以横向平铺。
    """
    p = Pen('skyline', 900, 80)
    for x, h, lean in ((60, 34, .1), (150, 52, .08), (505, 40, -.12), (720, 56, -.1), (872, 30, .1)):
        tree(p, x, 66, h, lean=lean, w=4.6 if h > 45 else 3.6)
    house(p, 215, 66, 40, 26, tilt=-.08)
    house(p, 268, 66, 28, 36, tilt=.07, window=False)
    house(p, 398, 66, 24, 40, tilt=.03, steep=1.3)
    p.line(412, 4, 412, 16, w=1.8, passes=1, jit=.3)
    p.line(408, 8, 416, 8, w=1.8, passes=1, jit=.3)
    house(p, 560, 66, 44, 28, tilt=.06)
    house(p, 616, 66, 26, 22, tilt=-.1, window=False)
    house(p, 806, 66, 36, 24, tilt=.07)
    for x in range(312, 366, 11):
        p.line(x, 66, x + p.j(1.5), 49 + p.j(3), w=2.2, passes=1)
    p.stroke([(308, 55), (336, 57), (366, 54)], w=1.6, passes=1)
    for x in (446, 464):
        p.fill([(x, 68), (x, 53), (x + 5, 48), (x + 10, 53), (x + 10, 68)], INK, jit=.5, shift=0)
    hill = [(-10, 62), (70, 58), (160, 63), (250, 59), (340, 64), (430, 58), (520, 63), (610, 59), (700, 64), (790, 59),
            (860, 63), (910, 62)]
    p.fill(hill + [(910, 96), (-10, 96)], INK, jit=.6, shift=0)
    return p.svg()


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
        ('token', token('t', '#b08d42', PAPER)),
        ('token_red', token('t-red', RED, '#d9b9a0')),
        ('token_dim', token('t-dim', '#5b4a30', '#8c8068')),
        ('token_dead', token('t-dead', '#6b655a', '#a49d8d')),
        ('token_empty', token('t-empty', None, None, line=CHALK, dashed=True)),
        ('token_empty_ink', token('t-empty-ink', None, None, line=INK, dashed=True)),
        ('ring_red', ring('r-red', '#b5463a')),
        ('ring_gold', ring('r-gold', '#d9b24a')),
        ('cross', cross('x')),
        ('mark_done', mark('m-done', True)), ('mark_wait', mark('m-wait', False)),
        ('moon', moon()), ('stars', stars()),
        ('potion_save', potion('p-save', '#86a54c', 'cross')),
        ('potion_poison', potion('p-poison', '#5d4a66', 'skull')),
        ('emblem_good', emblem_good()), ('emblem_wolf', emblem_wolf()),
        ('badge_sheriff', badge()), ('cardback', cardback()),
        ('dial', dial()), ('claw', claw()), ('line', line()), ('orn', orn()), ('skyline', skyline()),
    ]
