# -*- coding: utf-8 -*-
"""23 个角色的头像：大头、小身子、圆白眼、乱线排出来的阴影。

人和狼各有一副共用的「底稿」（bust / head / eyes，wolf_*），每个角色在底稿上
加帽子、头发、道具。画布是 200×200，重要内容都在中间的圆里（界面上多数地方裁成圆形）。
"""
from rough import Pen, INK, PAPER, BONE, mir, oval, arc, star, sample

SKIN = '#e2d0ad'
DARK = '#2b241d'
RED = '#8f3226'
GOLD = '#c2983c'
GREEN = '#6c7a48'
STEEL = '#8d9596'
BROWN = '#5b4532'
BOX = [(-4, -4), (204, -4), (204, 204), (-4, 204)]

HEAD = [(100, 36), (131, 44), (150, 70), (147, 102), (130, 130), (100, 146), (70, 130), (53, 102), (50, 70), (69, 44)]


# ------------------------------------------------------------------ 共用底稿

def backdrop(p, wash, moon=None):
    p.fill(BOX, PAPER, smooth=False, jit=0, shift=0)
    p.fill(oval(100, 104, 96, 94, n=9), wash, jit=7, op=.62, shift=3)
    if moon:
        p.shape(oval(100, 74, 80, 80, n=14), moon, w=2.2)
        p.hatch(oval(128, 96, 44, 50), angle=-30, gap=6, op=.3)
        for x, y, r in ((70, 40, 9), (128, 30, 6), (54, 84, 5)):
            p.stroke(oval(x, y, r, r * .8, n=7), closed=True, w=1.2, op=.5, passes=1)
    for tri, ang in (([(0, 0), (76, 0), (0, 76)], 45), ([(200, 0), (124, 0), (200, 76)], -45),
                     ([(0, 200), (0, 120), (80, 200)], -45), ([(200, 200), (200, 120), (120, 200)], 45)):
        p.hatch(tri, angle=ang, gap=5.5, op=.38, smooth=False)
    p.specks(26)


def bust(p, coat, neck=SKIN, w=3.0, shade=True):
    sh = [(18, 208), (28, 178), (56, 162), (84, 153), (100, 158), (116, 153), (144, 162), (172, 178), (182, 208)]
    p.shape(sh, coat, w=w)
    if shade:
        p.hatch([(104, 160), (146, 164), (174, 180), (182, 208), (110, 208)], angle=-50, gap=5, op=.4)
    if neck:
        p.shape([(87, 132), (113, 132), (115, 156), (100, 164), (85, 156)], neck, w=2.4)
        p.hatch([(87, 140), (113, 140), (114, 152), (86, 152)], angle=10, gap=3.5, op=.5, smooth=False)


def head(p, skin=SKIN, ears=True, w=3.0):
    if ears:
        p.shape(oval(49, 98, 7, 11, n=8), skin, w=2.2)
        p.shape(oval(151, 98, 7, 11, n=8), skin, w=2.2)
    p.shape(HEAD, skin, w=w)
    p.hatch([(120, 52), (148, 72), (146, 104), (128, 130), (106, 142), (124, 108), (130, 76)], angle=-58, gap=4.6, op=.36)


def eyes(p, kind='round', look=(0, 0), lid=0.0, color=BONE, r=13.0, y=94.0, dx=21.0, pupil=3.2, skin=SKIN,
         sizes=(1.0, 1.0), looks=None, only=None):
    for i, sx in enumerate((-1, 1)):
        if only is not None and only != sx:
            continue
        cx, rr = 100 + sx * dx, r * sizes[i]
        lk = looks[i] if looks else look
        p.hatch(oval(cx, y + 3, rr + 5, rr + 6, n=10), angle=62 * sx, gap=3.3, op=.42)   # 黑眼圈
        if kind == 'closed':
            p.stroke(arc(cx, y - 2, rr * .85, rr * .6, 20, 160), w=2.8)
            for a in (40, 90, 140):
                q = arc(cx, y - 2, rr * .85, rr * .6, a, a, n=1)[0]
                p.line(q[0], q[1], q[0] + (a - 90) * .05, q[1] + 5, w=1.4, passes=1)
            continue
        p.shape(oval(cx, y, rr, rr + 1, n=10), color, w=2.8)
        if kind == 'round':
            p.dot(cx + lk[0], y + lk[1], pupil)
        elif kind == 'heart':
            hx, hy = cx + lk[0], y + lk[1]
            p.fill([(hx, hy + 5), (hx - 5, hy - 1), (hx - 2.5, hy - 5), (hx, hy - 2), (hx + 2.5, hy - 5), (hx + 5, hy - 1)],
                   RED, jit=.3, shift=0)
        if lid:
            yl = y - rr + 2 * rr * lid
            cover = arc(cx, y, rr + 2, rr + 3, 180, 360, n=8) + [(cx + rr + 2, yl), (cx - rr - 2, yl)]
            p.fill(cover, skin, smooth=False, jit=.3, shift=0)
            p.line(cx - rr - 2, yl, cx + rr + 2, yl, w=2.6)
            p.stroke(arc(cx, y, rr, rr + 1, 200, 340, n=6), w=1.4, op=.5, passes=1)


def brows(p, tilt=0.0, y=72.0, w=3.2, color=INK, lift=(0.0, 0.0)):
    for i, sx in enumerate((-1, 1)):
        yy = y - lift[i]
        p.stroke([(100 + sx * 37, yy - tilt), (100 + sx * 24, yy - tilt * .2 - 2), (100 + sx * 9, yy + tilt)],
                 w=w, color=color, over=1.5)


def nose(p, big=False):
    if big:
        p.stroke([(101, 96), (93, 112), (97, 122), (107, 119)], w=2.6)
    else:
        p.stroke([(101, 102), (97, 113), (104, 115)], w=2.2)


def mouth(p, kind='flat', y=128.0):
    if kind == 'flat':
        p.line(88, y, 112, y, w=2.6)
    elif kind == 'frown':
        p.stroke(arc(100, y + 6, 13, 7, 200, 340, n=5), w=2.6)
    elif kind == 'smirk':
        p.stroke([(86, y + 1), (100, y + 3), (114, y - 4), (117, y - 8)], w=2.6)
    elif kind == 'o':
        p.shape(oval(100, y, 5, 6, n=7), DARK, w=2.0)
    elif kind == 'grin':
        g = [(82, y - 4), (100, y + 1), (120, y - 6), (115, y + 9), (99, y + 14), (85, y + 8)]
        p.shape(g, DARK, w=2.6)
        p.fill([(88, y - 1), (112, y - 2), (111, y + 3), (89, y + 3)], BONE, smooth=False, jit=.4, shift=0)
        for x in (94, 100, 106):
            p.line(x, y - 1, x, y + 3, w=1.1, passes=1)


def wolf_ears(p, fur, inner=DARK):
    e = [(60, 74), (44, 42), (40, 12), (66, 32), (90, 54)]
    i = [(62, 62), (52, 40), (49, 26), (64, 38), (78, 54)]
    for a, b in ((e, i), (mir(e), mir(i))):
        p.shape(a, fur, smooth=False, w=3.0)
        p.fill(b, inner, smooth=False, jit=.8, shift=.5)
        p.hatch(b, angle=70, gap=3.5, op=.5, smooth=False, color=BONE)


WOLF_R = [(122, 46), (142, 54), (154, 68), (160, 86), (176, 90), (164, 102), (180, 114), (162, 122), (168, 138),
          (148, 138), (136, 154), (120, 160), (114, 176)]
WOLF = [(100, 48)] + WOLF_R + [(100, 182)] + mir(WOLF_R)
MUZZLE = [(100, 102), (118, 112), (124, 134), (118, 156), (108, 172), (100, 176), (92, 172), (82, 156), (76, 134), (82, 112)]


def wolf_head(p, fur, muzzle, hatch=True):
    p.shape(WOLF, fur, smooth=False, w=3.2)
    if hatch:
        p.hatch([(126, 52), (156, 72), (176, 92), (166, 138), (138, 152), (126, 120), (132, 84)], angle=-55, gap=4.4,
                op=.42, smooth=False)
        p.hatch([(84, 50), (116, 50), (110, 72), (90, 72)], angle=88, gap=5, op=.4, smooth=False)
    p.shape(MUZZLE, muzzle, w=2.4)


def wolf_face(p, eye='#c9a13a', pupil='slit', fangs=True, brow=True, lid=0.0, fur=None, nose=DARK):
    for sx, e in ((-1, [(60, 95), (75, 84), (93, 97), (76, 105)]), (1, mir([(60, 95), (75, 84), (93, 97), (76, 105)]))):
        p.shape(e, eye, w=2.8)
        cx = 100 + sx * 23
        if pupil == 'slit':
            p.line(cx, 88, cx, 102, w=3.0, passes=1)
        elif pupil == 'dot':
            p.dot(cx, 95, 3.2)
        if lid and fur:
            p.fill([(100 + sx * 42, 82), (100 + sx * 5, 86), (100 + sx * 5, 86 + 18 * lid), (100 + sx * 42, 84 + 16 * lid)],
                   fur, smooth=False, jit=.4, shift=0)
            p.line(100 + sx * 42, 84 + 16 * lid, 100 + sx * 6, 86 + 18 * lid, w=2.6)
        if brow:
            p.stroke([(100 + sx * 46, 80), (100 + sx * 26, 78), (100 + sx * 6, 91)], w=4.0, over=2)
    p.shape([(88, 142), (112, 142), (106, 154), (100, 158), (94, 154)], nose, w=2.2)
    p.line(100, 158, 100, 166, w=2.2)
    m = [(100, 166), (90, 172), (79, 167), (71, 156)]
    p.stroke(m, w=2.6)
    p.stroke(mir(m), w=2.6)
    if fangs:
        t = [(83, 168), (87, 181), (92, 171)]
        p.shape(t, BONE, smooth=False, w=1.8)
        p.shape(mir(t), BONE, smooth=False, w=1.8)
    for sx in (-1, 1):                                             # 胡须点
        for k in range(3):
            p.dot(100 + sx * (11 + k * 4), 150 + (k % 2) * 5, 1.1)


def ruff(p, color, y=166.0, w=2.6):
    """脖子上一圈毛领 / 破布。"""
    z = [(24, 208), (30, y + 14), (46, y + 22), (52, y + 2), (68, y + 16), (78, y - 2), (92, y + 16), (100, y + 2),
         (108, y + 16), (122, y - 2), (132, y + 16), (148, y + 2), (154, y + 22), (170, y + 14), (176, 208)]
    p.shape(z, color, smooth=False, w=w)


# ------------------------------------------------------------------ 好人

def villager(p):
    backdrop(p, '#8d8c5c')
    bust(p, '#7b6b4b')
    p.line(70, 160, 76, 204, w=3.4)
    p.line(130, 160, 124, 204, w=3.4)
    head(p)
    p.shape(oval(100, 60, 76, 15, n=12, rot=-3), '#c9aa58', w=3.0)
    crown = [(60, 60), (64, 32), (84, 18), (116, 17), (136, 30), (140, 58), (100, 64)]
    p.shape(crown, '#d2b565', w=3.0)
    p.fill([(61, 50), (139, 48), (140, 58), (100, 64), (60, 60)], BROWN, jit=.6, shift=.5)
    p.hatch(crown, angle=12, gap=6, op=.45)
    for x, y, dx, dy in ((26, 62, -9, 4), (40, 71, -5, 8), (164, 66, 8, 6), (176, 58, 9, 2), (130, 74, 3, 8)):
        p.line(x, y, x + dx, y + dy, w=1.5, passes=1)
    eyes(p, look=(1, 3), lid=.28)
    brows(p, tilt=-3.5, y=78)
    nose(p)
    mouth(p, 'flat', y=127)
    p.stroke([(108, 127), (130, 120), (156, 108)], w=2.0)
    for k in range(4):
        x, y = 138 + k * 6, 117 - k * 3
        p.line(x, y, x + 5, y - 7, w=1.6, passes=1)
        p.line(x, y, x + 7, y + 2, w=1.6, passes=1)
    for x, y in ((66, 110), (72, 116), (62, 117), (128, 112), (135, 117)):
        p.dot(x, y, 1.2, op=.7)


def seer(p):
    backdrop(p, '#6f5d7e')
    bust(p, '#3f3549', neck=None)
    hood = [(100, 10), (140, 22), (164, 58), (168, 106), (154, 148), (128, 164), (100, 154), (72, 164), (46, 148),
            (32, 106), (36, 58), (60, 22)]
    p.shape(hood, '#4a3f58', w=3.2)
    p.hatch(hood, angle=-62, gap=5, op=.4)
    head(p, ears=False)
    p.fill([(52, 74), (68, 44), (100, 36), (132, 44), (148, 74), (128, 60), (100, 56), (72, 60)], INK, op=.5)
    eyes(p, look=(0, -5), pupil=2.6, r=14)
    brows(p, tilt=-2, y=74, w=2.4)
    nose(p)
    mouth(p, 'flat', y=129)
    eye3 = [(86, 58), (100, 49), (114, 58), (100, 66)]
    p.shape(eye3, BONE, w=2.2)
    p.dot(100, 58, 3)
    for a in (-60, -90, -120):
        q = arc(100, 58, 17, 15, a, a, n=1)[0]
        p.line(q[0], q[1], q[0] + (q[0] - 100) * .35, q[1] - 5, w=1.4, passes=1)
    ball = oval(150, 168, 28, 28, n=12)
    p.shape(ball, '#a8b8b4', w=3.0)
    p.hatch(oval(158, 176, 18, 18), angle=-40, gap=4, op=.4)
    p.stroke(arc(142, 160, 13, 13, 180, 280, n=5), w=2.4, color=BONE, passes=1)
    p.stroke([(146, 170), (154, 164), (160, 172), (152, 178), (146, 172)], w=1.4, op=.6, passes=1)
    p.shape([(126, 192), (174, 192), (180, 208), (120, 208)], BROWN, smooth=False, w=2.4)


def witch(p):
    backdrop(p, '#717d54')
    drape = [(60, 48), (42, 90), (32, 142), (38, 182), (58, 164), (64, 120), (62, 84)]
    for d in (drape, mir(drape)):
        p.shape(d, DARK, w=2.6)
        p.hatch(d, angle=80, gap=5, op=.45, color=BONE)
    bust(p, '#2f3429', neck='#cfd0a8')
    head(p, skin='#cfd0a8')
    eyes(p, look=(2, 1), lid=.2, skin='#cfd0a8', pupil=2.6, sizes=(1.0, .82))
    brows(p, tilt=5, y=73)
    nose(p, big=True)
    p.dot(109, 111, 1.6)
    mouth(p, 'smirk', y=132)
    p.shape([(104, 131), (109, 130), (108, 137), (104, 137)], BONE, smooth=False, w=1.4)
    p.shape(oval(100, 54, 80, 14, n=12, rot=-4), DARK, w=3.0)
    cone = [(62, 54), (76, 28), (94, 8), (126, -2), (152, 10), (134, 14), (126, 26), (138, 52), (100, 60)]
    p.shape(cone, '#352e27', w=3.0)
    p.hatch(cone, angle=-70, gap=5, op=.4, color=BONE)
    p.fill([(64, 44), (134, 42), (138, 53), (100, 60), (62, 55)], '#5d4a66', jit=.6, shift=.5)
    p.shape([(92, 43), (108, 43), (108, 58), (92, 58)], GOLD, smooth=False, w=2.0)
    flask = oval(46, 174, 17, 17, n=10)
    p.shape([(40, 150), (52, 150), (52, 162), (40, 162)], BONE, smooth=False, w=2.0)
    p.shape(flask, '#86a54c', w=2.8)
    p.hatch(oval(50, 180, 10, 10), angle=-40, gap=3.5, op=.45)
    p.shape([(39, 144), (53, 144), (52, 151), (40, 151)], BROWN, smooth=False, w=2.0)
    for x, y, r in ((30, 138, 2.4), (40, 128, 1.8), (26, 122, 1.4)):
        p.stroke(oval(x, y, r, r, n=6), closed=True, w=1.2, passes=1, op=.7)


def hunter(p):
    backdrop(p, '#8d7150')
    gun = [(158, 208), (174, 56), (184, 56), (172, 208)]
    p.shape(gun, '#3b342c', smooth=False, w=2.6)
    p.shape([(172, 44), (186, 44), (186, 58), (172, 58)], STEEL, smooth=False, w=2.0)
    bust(p, BROWN)
    ruff(p, '#b9aa8c', y=152)
    head(p)
    p.specks(60, op=.5, r=(.6, 1.4), box=(64, 112, 136, 142))
    eyes(p, look=(0, 2), lid=.42, pupil=3)
    brows(p, tilt=6, y=74, w=4)
    nose(p)
    mouth(p, 'frown', y=127)
    p.line(118, 104, 140, 122, w=2.0)
    for k in range(3):
        p.line(122 + k * 6, 112 + k * 5, 127 + k * 6, 106 + k * 5, w=1.3, passes=1)
    p.shape(oval(100, 57, 72, 13, n=12, rot=5), '#4b3c2b', w=3.0)
    crown = [(64, 54), (68, 28), (100, 16), (132, 26), (138, 58), (100, 62)]
    p.shape(crown, '#5a4833', w=3.0)
    p.hatch(crown, angle=-65, gap=5, op=.4)
    p.fill([(65, 46), (136, 48), (138, 58), (100, 62), (64, 56)], DARK, jit=.6, shift=.5)
    feather = [(128, 44), (140, 22), (158, 4), (162, 22), (150, 38)]
    p.shape(feather, RED, w=2.2)
    p.line(130, 44, 158, 8, w=1.4, passes=1)


def guard(p):
    backdrop(p, '#73838a')
    bust(p, STEEL)
    for x in (40, 62, 138, 160):
        p.dot(x, 180, 2.2)
    p.shape([(74, 150), (126, 150), (130, 168), (100, 176), (70, 168)], '#767e80', w=2.6)
    head(p)
    eyes(p, look=(0, 1), lid=.15, pupil=3)
    nose(p)
    stache = [(100, 120), (84, 117), (68, 126), (70, 132), (86, 128), (100, 127), (114, 128), (130, 132), (132, 126), (116, 117)]
    p.shape(stache, '#4b3c2b', w=2.4)
    mouth(p, 'frown', y=136)
    helm = [(46, 86), (49, 52), (69, 27), (100, 19), (131, 27), (151, 52), (154, 86), (128, 78), (100, 75), (72, 78)]
    p.shape(helm, '#9aa1a2', w=3.2)
    p.hatch([(104, 22), (132, 28), (151, 52), (153, 84), (128, 76), (124, 48)], angle=-60, gap=4.6, op=.42)
    p.shape([(42, 80), (72, 72), (100, 69), (128, 72), (158, 80), (156, 90), (128, 82), (100, 79), (72, 82), (44, 90)],
            '#767e80', w=2.6)
    p.shape([(94, 76), (106, 76), (105, 114), (95, 114)], '#9aa1a2', smooth=False, w=2.6)
    for x in (56, 78, 122, 144):
        p.dot(x, 81 - abs(x - 100) * .04, 1.8)
    shield = [(10, 124), (76, 126), (80, 168), (46, 208), (8, 184)]
    p.shape(shield, '#6c4c33', w=3.2)
    p.hatch(shield, angle=86, gap=9, op=.45)
    p.shape(oval(44, 160, 11, 11, n=8), STEEL, w=2.4)
    p.stroke([(14, 130), (72, 132), (75, 166), (46, 200), (13, 182)], closed=True, w=1.6, op=.6, passes=1)


def idiot(p):
    backdrop(p, '#a96c42')
    bust(p, RED)
    p.fill([(100, 158), (144, 162), (172, 178), (182, 208), (100, 208)], GOLD, shift=.5)
    p.hatch([(104, 160), (146, 164), (174, 180), (182, 208), (110, 208)], angle=-50, gap=5, op=.4)
    ruff(p, BONE, y=150)
    head(p)
    eyes(p, sizes=(1.2, .78), looks=((5, 4), (-3, -3)), pupil=3.4)
    brows(p, tilt=-4, y=70, lift=(4, -3), w=2.8)
    nose(p)
    mouth(p, 'grin', y=126)
    p.shape([(96, 134), (108, 133), (110, 146), (102, 151), (95, 145)], '#b5574a', w=1.8)
    for sx in (-1, 1):
        p.stroke(arc(100 + sx * 36, 118, 5, 4, 0, 500, n=9), w=1.4, color=RED, passes=1)
    hl = [(58, 66), (40, 40), (16, 34), (6, 56), (16, 70), (26, 54), (40, 58), (62, 78)]
    hr = [(142, 66), (158, 34), (184, 22), (198, 42), (192, 60), (180, 44), (164, 52), (138, 78)]
    p.shape(hl, RED, w=3.0)
    p.shape(hr, GOLD, w=3.0)
    band = [(52, 72), (74, 54), (100, 48), (126, 54), (148, 72), (128, 66), (100, 62), (72, 66)]
    p.shape(band, BONE, w=2.8)
    p.shape([(100, 48), (112, 22), (124, 50)], RED, w=2.6)
    for x, y in ((12, 72), (192, 64), (112, 20)):
        p.shape(oval(x, y, 6, 6, n=7), GOLD, w=2.2)
        p.line(x - 3, y + 2, x + 3, y + 2, w=1.2, passes=1)


def knight(p):
    backdrop(p, '#62707d')
    blade = [(162, 208), (163, 92), (168, 80), (173, 92), (174, 208)]
    p.shape(blade, BONE, smooth=False, w=2.4)
    p.line(168, 96, 168, 204, w=1.2, passes=1, op=.6)
    bust(p, STEEL, neck=None)
    for sx in (-1, 1):
        pad = oval(100 + sx * 58, 176, 30, 22, n=10)
        p.shape(pad, '#9aa1a2', w=3.0)
        p.hatch(oval(100 + sx * 58 + 8, 182, 18, 13), angle=-50, gap=4.4, op=.4)
        p.dot(100 + sx * 58, 168, 2.2)
    helm = [(52, 34), (76, 24), (100, 21), (124, 24), (148, 34), (152, 118), (130, 148), (100, 156), (70, 148), (48, 118)]
    p.shape(helm, '#a3a9a8', w=3.4)
    p.hatch([(106, 24), (146, 36), (150, 118), (130, 146), (108, 152), (118, 96)], angle=-60, gap=4.6, op=.42)
    p.shape([(56, 82), (144, 82), (144, 97), (56, 97)], DARK, smooth=False, w=2.6)
    p.dot(80, 90, 3.6, color=BONE)
    p.dot(120, 90, 3.6, color=BONE)
    p.shape([(95, 40), (105, 40), (106, 152), (94, 152)], '#8d9596', smooth=False, w=2.4)
    for r in range(3):
        for c in range(3):
            p.dot(116 + c * 9, 112 + r * 9, 1.6)
            p.dot(66 + c * 9, 112 + r * 9, 1.6)
    for x in (58, 78, 122, 142):
        p.dot(x, 72, 2.0)
    plume = [(96, 26), (86, 6), (102, -4), (114, 8), (130, -6), (136, 10), (152, 6), (144, 22), (120, 22)]
    p.shape(plume, RED, w=2.8)
    p.hatch(plume, angle=70, gap=5, op=.4)
    p.shape([(152, 92), (184, 92), (184, 100), (152, 100)], GOLD, smooth=False, w=2.4)


def psychic(p):
    backdrop(p, '#4f5976')
    veil = [(54, 66), (36, 116), (38, 176), (60, 164), (60, 110)]
    for d in (veil, mir(veil)):
        p.shape(d, '#6c5270', w=2.6)
        p.hatch(d, angle=84, gap=5.5, op=.4)
    bust(p, '#3a415c')
    head(p)
    eyes(p, kind='closed', r=14, y=98)
    brows(p, tilt=-2.5, y=80, w=2.4)
    nose(p)
    mouth(p, 'o', y=130)
    turban = [(46, 78), (52, 42), (76, 20), (108, 14), (140, 26), (154, 56), (154, 80), (128, 68), (100, 64), (72, 68)]
    p.shape(turban, '#7c5c7e', w=3.2)
    for a in ([(54, 50), (90, 44), (130, 60)], [(64, 32), (104, 30), (148, 52)], [(52, 68), (84, 56), (112, 58)]):
        p.stroke(a, w=1.8, op=.7)
    p.hatch([(110, 16), (140, 26), (154, 56), (154, 78), (132, 68)], angle=-58, gap=4.6, op=.4)
    eye3 = [(82, 52), (100, 40), (118, 52), (100, 62)]
    p.shape(eye3, BONE, w=2.6)
    p.shape(oval(100, 51, 5.5, 6, n=7), GOLD, w=1.6)
    p.dot(100, 51, 2.4)
    for a in range(200, 350, 28):
        q = arc(100, 52, 22, 17, a, a, n=1)[0]
        p.line(q[0], q[1], q[0] + (q[0] - 100) * .3, q[1] + (q[1] - 52) * .45, w=1.4, passes=1)
    p.shape([(148, 150), (164, 150), (166, 208), (146, 208)], BONE, smooth=False, w=2.6)
    p.stroke([(150, 156), (152, 170), (156, 162)], w=1.4, passes=1)
    flame = [(156, 148), (148, 136), (156, 116), (164, 134)]
    p.shape(flame, GOLD, w=2.4)
    p.line(156, 150, 156, 142, w=1.6, passes=1)
    for a in range(180, 361, 36):
        q = arc(156, 132, 22, 22, a, a, n=1)[0]
        p.line(q[0], q[1], q[0] + (q[0] - 156) * .3, q[1] + (q[1] - 132) * .3, w=1.2, passes=1, op=.6)


def gravekeeper(p):
    backdrop(p, '#6f7768')
    p.line(160, 208, 174, 44, w=4.0)
    spade = [(160, 46), (186, 46), (186, 20), (174, 4), (162, 20)]
    p.shape(spade, STEEL, w=2.8)
    p.hatch(spade, angle=-60, gap=4.4, op=.4)
    bust(p, '#3b3b35', neck='#d3c7ad')
    p.shape([(66, 158), (86, 132), (96, 164)], '#4a4a42', w=2.6)
    p.shape([(134, 158), (114, 132), (104, 164)], '#4a4a42', w=2.6)
    head(p, skin='#d3c7ad')
    eyes(p, look=(-1, 3), lid=.38, skin='#d3c7ad', pupil=2.6, r=12)
    for sx in (-1, 1):
        b = [(100 + sx * 40, 70), (100 + sx * 26, 62), (100 + sx * 8, 74), (100 + sx * 24, 78)]
        p.shape(b, BONE, w=2.2)
        p.hatch(b, angle=75, gap=3, op=.45)
    nose(p, big=True)
    st = [(100, 122), (84, 120), (72, 134), (68, 152), (78, 144), (88, 130), (100, 130), (112, 130), (122, 144),
          (132, 152), (128, 134), (116, 120)]
    p.shape(st, BONE, w=2.4)
    p.hatch(st, angle=80, gap=3.4, op=.4)
    cap = [(48, 68), (56, 42), (86, 28), (124, 30), (148, 46), (152, 62), (170, 72), (140, 76), (100, 66), (70, 70)]
    p.shape(cap, '#4b473d', w=3.2)
    p.hatch(cap, angle=-62, gap=4.6, op=.4, color=BONE)
    lamp = [(22, 150), (58, 150), (62, 196), (18, 196)]
    p.stroke(arc(40, 150, 14, 16, 180, 360, n=6), w=2.2)
    for a in range(0, 360, 30):
        q = arc(40, 172, 34, 34, a, a, n=1)[0]
        p.line(q[0], q[1], q[0] + (q[0] - 40) * .22, q[1] + (q[1] - 172) * .22, w=1.2, passes=1, op=.55)
    p.shape(lamp, GOLD, smooth=False, w=2.8)
    p.shape([(16, 144), (64, 144), (62, 152), (18, 152)], DARK, smooth=False, w=2.2)
    p.shape([(14, 194), (66, 194), (66, 204), (14, 204)], DARK, smooth=False, w=2.2)
    p.line(40, 152, 40, 194, w=1.6, passes=1)
    p.shape([(40, 184), (34, 174), (40, 160), (46, 174)], BONE, w=1.6)


def dreamer(p):
    backdrop(p, '#414f69')
    p.shape([(20, 22), (34, 12), (30, 30), (40, 44), (24, 46), (12, 36)], BONE, w=2.2)
    for x, y, s in ((46, 22, 7), (58, 10, 5)):
        p.stroke([(x, y), (x + s, y), (x, y + s), (x + s, y + s)], smooth=False, w=1.8, passes=1)
    bust(p, '#b9b7a6')
    for y in (170, 184, 198):
        p.dot(100, y, 2.2)
    p.line(100, 160, 100, 206, w=1.4, passes=1, op=.6)
    for x, y in ((62, 60), (54, 74), (140, 66)):
        p.shape([(x, y), (x - 10, y + 4), (x - 4, y + 12), (x + 6, y + 8)], DARK, w=2.0)
    head(p)
    eyes(p, look=(0, 5), lid=.56, pupil=3)
    brows(p, tilt=-4, y=72, w=2.4)
    nose(p)
    mouth(p, 'o', y=129)
    cap = [(48, 74), (55, 44), (82, 24), (116, 22), (144, 36), (166, 64), (180, 100), (170, 106), (150, 80), (130, 68),
           (100, 63), (70, 67)]
    p.shape(cap, '#5f718c', w=3.2)
    for a in ([(64, 34), (86, 48), (98, 64)], [(92, 22), (112, 42), (126, 66)], [(124, 26), (142, 50), (152, 80)],
              [(152, 46), (164, 72), (172, 102)]):
        p.stroke(a, w=3.0, color=BONE, passes=1, op=.8)
    p.shape([(44, 70), (70, 62), (100, 58), (130, 63), (152, 78), (150, 88), (128, 74), (100, 69), (72, 73), (46, 82)],
            BONE, w=2.6)
    p.shape(oval(176, 110, 10, 10, n=8), BONE, w=2.6)
    p.hatch(oval(178, 113, 6, 6), angle=-40, gap=3, op=.45)


def magician(p):
    backdrop(p, '#7c4652')
    p.line(14, 196, 60, 150, w=5.0)
    p.line(48, 162, 60, 150, w=5.0, color=BONE, passes=1)
    for x, y, r in ((70, 136, 5), (56, 128, 3.5), (76, 150, 3)):
        p.shape(star(x, y, r, r * .4, 4), BONE, smooth=False, w=1.2)
    bust(p, DARK)
    p.shape([(84, 154), (116, 154), (108, 208), (92, 208)], BONE, smooth=False, w=2.2)
    bow = [(100, 164), (82, 154), (80, 176), (100, 168), (120, 176), (118, 154)]
    p.shape(bow, RED, smooth=False, w=2.4)
    for sx in (-1, 1):
        p.shape([(100 + sx * 48, 64), (100 + sx * 54, 84), (100 + sx * 46, 104), (100 + sx * 40, 82)], DARK, w=2.2)
    head(p)
    eyes(p, look=(4, 0), pupil=2.8, lid=.12)
    brows(p, tilt=3, y=73, lift=(0, 7), w=3)
    nose(p)
    for sx in (-1, 1):
        c = [(100, 121), (100 + sx * 14, 117), (100 + sx * 28, 123), (100 + sx * 34, 114), (100 + sx * 28, 108),
             (100 + sx * 24, 113)]
        p.stroke(c, w=3.4)
    mouth(p, 'smirk', y=131)
    p.shape([(94, 138), (106, 138), (100, 152)], DARK, w=2.0)
    p.shape(oval(100, 54, 60, 11, n=12, rot=-6), DARK, w=3.0)
    cyl = [(68, 52), (62, 0), (132, -8), (134, 48), (100, 56)]
    p.shape(cyl, '#352e27', w=3.2)
    p.hatch(cyl, angle=-72, gap=5, op=.4, color=BONE)
    p.fill([(67, 40), (134, 34), (134, 48), (100, 56), (68, 52)], RED, jit=.6, shift=.5)
    card = [(112, 14), (132, 8), (138, 34), (118, 40)]
    p.shape(card, BONE, smooth=False, w=2.0)
    p.shape([(125, 17), (130, 24), (125, 31), (120, 24)], RED, smooth=False, w=1.0)


def witcher(p):
    backdrop(p, '#415c5a')
    p.line(26, 208, 44, 60, w=4.0)
    p.shape([(28, 64), (62, 70), (61, 78), (27, 72)], STEEL, smooth=False, w=2.2)
    p.shape(oval(46, 54, 6, 6, n=7), STEEL, w=2.2)
    hair = [(56, 56), (44, 100), (40, 150), (56, 158), (62, 110)]
    for d in (hair, mir(hair)):
        p.shape(d, '#b6ae99', w=2.6)
        p.hatch(d, angle=82, gap=4.4, op=.45)
    bust(p, '#3b3128')
    head(p)
    p.specks(46, op=.5, r=(.6, 1.3), box=(66, 114, 134, 142))
    eyes(p, look=(0, 1), lid=.4, pupil=3, only=1)
    p.shape([(60, 84), (94, 84), (92, 106), (78, 112), (62, 104)], DARK, w=2.6)
    p.line(50, 78, 150, 70, w=2.0)
    brows(p, tilt=6, y=73, w=4)
    nose(p)
    mouth(p, 'frown', y=128)
    p.line(126, 80, 136, 122, w=1.8)
    for k in range(3):
        p.line(125 + k * 3, 90 + k * 10, 133 + k * 3, 88 + k * 10, w=1.2, passes=1)
    for sx in (-1, 1):
        p.shape([(100 + sx * 44, 162), (100 + sx * 20, 122), (100 + sx * 8, 162)], '#4b3f33', w=2.8)
    p.shape(oval(100, 56, 86, 12, n=12, rot=2), '#2b2620', w=3.0)
    crown = [(64, 54), (72, 10), (128, 8), (136, 52), (100, 60)]
    p.shape(crown, '#352e27', w=3.2)
    p.hatch(crown, angle=-70, gap=5, op=.4, color=BONE)
    p.fill([(65, 40), (135, 38), (136, 52), (100, 60), (64, 54)], BROWN, jit=.6, shift=.5)
    p.shape([(90, 38), (110, 38), (110, 56), (90, 56)], GOLD, smooth=False, w=2.2)


def cupid(p):
    backdrop(p, '#a9737c')
    wing = [(44, 156), (10, 132), (2, 92), (18, 62), (36, 84), (46, 70), (58, 104), (62, 140)]
    for d in (wing, mir(wing)):
        p.shape(d, BONE, w=2.8)
        p.hatch(d, angle=70, gap=6, op=.4)
    for cx, cy, r in ((58, 62, 17), (74, 40, 18), (100, 32, 19), (126, 40, 18), (142, 62, 17), (48, 86, 13), (152, 86, 13)):
        p.shape(oval(cx, cy, r, r, n=9), '#b98b4b', w=2.6)
    bust(p, SKIN)
    p.shape([(52, 164), (74, 156), (150, 208), (118, 208)], RED, smooth=False, w=2.6)
    head(p)
    for cx, cy, r in ((70, 54, 12), (90, 46, 12), (112, 46, 12), (132, 56, 11)):
        p.shape(oval(cx, cy, r, r, n=8), '#c79a57', w=2.4)
        p.stroke(arc(cx, cy, r * .5, r * .5, 0, 400, n=8), w=1.2, passes=1, op=.6)
    eyes(p, kind='heart', look=(1, 1), r=14)
    brows(p, tilt=-2, y=72, lift=(0, 5), w=2.6)
    nose(p)
    mouth(p, 'smirk', y=129)
    for sx in (-1, 1):
        p.hatch(oval(100 + sx * 34, 116, 9, 6), angle=-40, gap=3, op=.6, color=RED, w=1.3)
    p.line(118, 204, 190, 132, w=2.6)
    heart = [(190, 132), (176, 126), (176, 112), (186, 114), (192, 108), (200, 118), (198, 130)]
    p.shape(heart, RED, w=2.4)
    for k in range(3):
        p.line(124 + k * 5, 198 - k * 5, 116 + k * 5, 196 - k * 5, w=1.4, passes=1)


def mixed(p):
    """混血儿：左半张是人脸，右半张是狼脸，中间一道缝线。"""
    fur, muzzle = '#6f675c', '#9c8f79'
    backdrop(p, '#7d7766')
    bust(p, '#5c544a')
    ruff(p, '#8d7a5c', y=160)
    # 右边一只狼耳朵，左边一只人耳朵（先画耳朵，脑袋盖住耳根）
    e = mir([(60, 74), (44, 42), (40, 12), (66, 32), (90, 54)])
    i = mir([(62, 62), (52, 40), (49, 26), (64, 38), (78, 54)])
    p.shape(e, fur, smooth=False, w=3.0)
    p.fill(i, DARK, smooth=False, jit=.8, shift=.5)
    p.hatch(i, angle=-70, gap=3.5, op=.5, smooth=False, color=BONE)
    p.shape(oval(49, 98, 7, 11, n=8), SKIN, w=2.2)
    p.shape(HEAD, SKIN, w=3.0)
    # 右半张脸铺成狼毛：沿着脑袋的轮廓取右半边，再沿中线的缝补回去
    outline = sample(HEAD, closed=True)
    right = [q for q in outline[:outline.index(min(outline, key=lambda q: abs(q[0] - 100) + abs(q[1] - 146)))]
             if q[0] >= 99]
    seam = [(100, 146), (97, 134), (103, 122), (97, 108), (103, 94), (97, 80), (103, 66), (97, 52), (100, 38)]
    half = right + seam
    p.fill(half, fur, smooth=False, jit=.6, shift=.8)
    p.hatch(half, angle=-55, gap=4.2, op=.45, smooth=False)
    p.fill([(104, 108), (124, 110), (134, 124), (120, 136), (104, 138)], muzzle, jit=.6, shift=.5, op=.9)
    for k in range(5):                                             # 右边脸颊上翘起来的毛
        x, y = 146 - k * 2, 66 + k * 14
        p.line(x, y, x + 10, y - 4, w=1.6, passes=1)
    p.stroke(seam, w=2.2, smooth=False)
    for k in range(4):                                             # 缝线上的针脚
        y = 58 + k * 22
        p.line(93, y, 107, y + 3, w=1.4, passes=1)
    # 左边：人的头发
    hair = [(52, 74), (50, 50), (66, 32), (88, 26), (100, 30), (98, 46), (88, 40), (80, 54), (70, 48), (62, 64)]
    p.shape(hair, BROWN, w=2.6)
    p.hatch(hair, angle=60, gap=5, op=.4)
    # 眼睛：左边圆眼，右边狼眼
    eyes(p, look=(2, 2), only=-1)
    p.stroke([(62, 74), (76, 70), (91, 75)], w=3.2, over=1.5)
    we = mir([(60, 95), (75, 84), (93, 97), (76, 105)])
    p.shape(we, '#c9a13a', w=2.8)
    p.line(123, 87, 123, 103, w=3.0, passes=1)
    p.stroke([(146, 80), (126, 77), (107, 89)], w=4.0, over=2)
    nose(p)
    # 嘴：左边平平的，右边咧开露出一颗獠牙
    p.line(84, 128, 100, 128, w=2.6)
    p.stroke([(100, 128), (110, 126), (120, 119)], w=2.6)
    p.shape([(105, 127), (108, 138), (113, 126)], BONE, smooth=False, w=1.8)
    for k in range(3):                                             # 胡须点
        p.dot(114 + k * 5, 114 + (k % 2) * 5, 1.1)


# ------------------------------------------------------------------ 狼人

def wolf(p):
    backdrop(p, '#7c7162')
    bust(p, '#5c544a', neck=None)
    ruff(p, RED, y=168)
    wolf_ears(p, '#6f675c')
    wolf_head(p, '#6f675c', '#b8ab93')
    wolf_face(p)


def wolfking(p):
    backdrop(p, '#9b7e3d')
    bust(p, RED, neck=None)
    ruff(p, BONE, y=166)
    for x, y in ((40, 196), (64, 190), (136, 190), (160, 196), (100, 192)):
        p.dot(x, y, 2.4)
    wolf_ears(p, '#4b4239')
    wolf_head(p, '#4b4239', '#9c8f79')
    wolf_face(p, eye='#d6a93a')
    p.line(64, 70, 86, 112, w=2.4)
    for k in range(3):
        p.line(66 + k * 7, 82 + k * 10, 76 + k * 7, 78 + k * 10, w=1.4, passes=1)
    crown = [(68, 52), (62, 14), (82, 32), (100, 6), (118, 32), (138, 14), (132, 52), (100, 58)]
    p.shape(crown, GOLD, smooth=False, w=3.0)
    p.hatch([(104, 10), (118, 32), (138, 16), (132, 52), (104, 56)], angle=-60, gap=4.4, op=.42, smooth=False)
    p.line(68, 44, 132, 44, w=1.6, passes=1)
    for x in (82, 100, 118):
        p.shape(oval(x, 49, 3.6, 3.6, n=6), RED, w=1.4)


def whitewolf(p):
    backdrop(p, '#8fa1a9')
    bust(p, '#c9c4b6', neck=None)
    ruff(p, '#e9e3d3', y=168)
    wolf_ears(p, '#e6dfcd', inner='#9fb4bd')
    wolf_head(p, '#e6dfcd', '#f4eedf')
    wolf_face(p, eye='#a9c0c8')
    for tri in ([(72, 54), (76, 24), (88, 52)], [(90, 52), (100, 12), (110, 52)], [(112, 52), (124, 24), (128, 54)]):
        p.shape(tri, '#b9cdd3', smooth=False, w=2.4)
        p.line(tri[1][0], tri[1][1] + 6, (tri[0][0] + tri[2][0]) / 2.0, tri[0][1] - 2, w=1.1, passes=1, op=.6)
    for x, y in ((134, 170), (146, 162), (140, 182)):
        p.stroke(arc(x, y, 5, 4, 0, 420, n=8), w=1.3, passes=1, op=.7)
    for x, y in ((26, 96), (176, 60), (168, 150)):
        p.line(x - 5, y, x + 5, y, w=1.3, passes=1)
        p.line(x, y - 5, x, y + 5, w=1.3, passes=1)
        p.line(x - 3.5, y - 3.5, x + 3.5, y + 3.5, w=1.1, passes=1)


def beauty(p):
    backdrop(p, '#a9737c')
    bust(p, '#5d4a52', neck=None)
    ruff(p, '#cdb7a6', y=170)
    wolf_ears(p, '#b89b8d', inner='#8f5a62')
    wolf_head(p, '#b89b8d', '#e6d6c4')
    wolf_face(p, eye='#b3566f', pupil='dot', brow=False, lid=.42, fur='#b89b8d')
    for sx in (-1, 1):
        for k in range(3):
            x = 100 + sx * (40 - k * 9)
            p.line(x, 90 - k * .5, x + sx * 5, 80 - k, w=1.6, passes=1)
    p.dot(126, 128, 1.8)
    for k in range(9):
        x = 60 + k * 10
        p.shape(oval(x, 186 + abs(k - 4) * -1.6 + 6, 4.4, 4.4, n=6), BONE, w=1.4)
    rose = oval(52, 44, 15, 15, n=9)
    p.shape([(38, 56), (22, 62), (30, 46)], GREEN, w=2.0)
    p.shape([(60, 60), (72, 70), (56, 68)], GREEN, w=2.0)
    p.shape(rose, RED, w=2.6)
    p.stroke(arc(52, 44, 9, 9, 0, 620, n=14), w=1.5, passes=1)


def nightmare(p):
    backdrop(p, '#5f4c68')
    wing = [(40, 150), (4, 150), (10, 96), (24, 124), (34, 96), (44, 124), (58, 104), (60, 146)]
    for d in (wing, mir(wing)):
        p.shape(d, '#2f2735', smooth=False, w=2.8)
        p.hatch(d, angle=80, gap=5, op=.4, color=BONE, smooth=False)
    bust(p, '#2f2735', neck=None)
    ruff(p, '#3d3345', y=168)
    wolf_ears(p, '#3c3243', inner='#6f5d7e')
    wolf_head(p, '#3c3243', '#716080')
    wolf_face(p, eye=BONE, pupil=None)
    horn = [(74, 50), (56, 26), (32, 22), (16, 40), (22, 62), (38, 66), (34, 50), (44, 44), (56, 52), (66, 64)]
    for d in (horn, mir(horn)):
        p.shape(d, '#b6ae99', w=2.8)
        p.hatch(d, angle=30, gap=4.2, op=.5)


def bloodmoon(p):
    backdrop(p, '#5c2c28', moon=RED)
    for x, y, ln in ((40, 126, 22), (58, 140, 14), (150, 132, 20), (166, 120, 12)):
        p.line(x, y, x, y + ln, w=2.4, color=RED, passes=1)
        p.dot(x, y + ln + 2, 2.2, color=RED)
    bust(p, '#2e2622', neck=None)
    ruff(p, '#3a2f2b', y=168)
    wolf_ears(p, '#3b302c', inner=RED)
    wolf_head(p, '#3b302c', '#7c6c5f')
    wolf_face(p, eye='#d9573f', pupil='dot')
    hoodl = [(100, 44), (70, 42), (48, 60), (38, 96), (52, 82), (72, 66), (100, 60)]
    p.shape(hoodl + mir(hoodl)[1:-1], '#2a2320', w=3.0)
    p.hatch([(104, 46), (130, 44), (152, 60), (160, 92), (146, 80), (128, 66), (104, 60)], angle=-58, gap=4.2, op=.45,
            color=BONE)


def ghostrider(p):
    backdrop(p, '#3b342d')
    fl = [(34, 96), (14, 50), (40, 64), (44, 16), (70, 48), (100, -4), (130, 48), (156, 16), (160, 64), (186, 50),
          (166, 96), (100, 110)]
    p.shape(fl, '#c9763c', w=3.0)
    fi = [(56, 92), (46, 62), (62, 70), (68, 38), (86, 62), (100, 28), (114, 62), (132, 38), (138, 70), (154, 62),
          (144, 92), (100, 104)]
    p.shape(fi, GOLD, w=2.2)
    bust(p, '#2b241d', neck=None)
    for sx in (-1, 1):
        for k in range(3):
            x = 100 + sx * (34 + k * 22)
            p.shape([(x - 7, 190 - k * 6), (x, 166 - k * 4), (x + 7, 190 - k * 6)], STEEL, smooth=False, w=2.2)
    wolf_ears(p, BONE, inner='#b6ae99')
    wolf_head(p, BONE, '#f1ead8', hatch=False)
    p.hatch([(126, 52), (156, 72), (176, 92), (166, 138), (138, 152), (126, 120), (132, 84)], angle=-55, gap=5, op=.35,
            smooth=False)
    for sx in (-1, 1):
        s = [(100 + sx * 46, 92), (100 + sx * 30, 76), (100 + sx * 8, 92), (100 + sx * 14, 110), (100 + sx * 36, 112)]
        p.shape(s, DARK, w=2.8)
        p.dot(100 + sx * 26, 96, 4, color='#d9743c')
        p.dot(100 + sx * 26, 96, 1.6, color=GOLD)
    p.shape([(92, 140), (108, 140), (100, 158)], DARK, smooth=False, w=2.2)
    jaw = [(72, 158), (78, 170), (84, 160), (90, 174), (96, 162), (100, 176), (104, 162), (110, 174), (116, 160),
           (122, 170), (128, 158)]
    p.stroke(jaw, smooth=False, w=2.6)
    p.stroke([(104, 54), (98, 70), (106, 78), (100, 92)], smooth=False, w=1.6, passes=1)
    p.stroke([(140, 110), (150, 120), (146, 132)], smooth=False, w=1.4, passes=1)


def gargoyle(p):
    backdrop(p, '#6f7768')
    wing = [(46, 170), (6, 176), (10, 108), (22, 76), (34, 110), (46, 96), (56, 128), (62, 160)]
    for d in (wing, mir(wing)):
        p.shape(d, '#5d6056', smooth=False, w=2.8)
        p.hatch(d, angle=76, gap=5, op=.45, smooth=False)
    bust(p, '#74776b', neck=None)
    p.shape([(30, 190), (170, 190), (176, 208), (24, 208)], '#5d6056', smooth=False, w=2.8)
    wolf_ears(p, '#8b8e81', inner='#5d6056')
    wolf_head(p, '#8b8e81', '#a4a798')
    wolf_face(p, eye=BONE, pupil=None)
    for sx in (-1, 1):
        h = [(100 + sx * 16, 52), (100 + sx * 22, 26), (100 + sx * 32, 50)]
        p.shape(h, '#a4a798', smooth=False, w=2.4)
    p.stroke([(120, 50), (128, 66), (122, 76), (132, 90), (128, 100)], smooth=False, w=1.8)
    p.stroke([(58, 108), (66, 118), (60, 128), (70, 140)], smooth=False, w=1.6, passes=1)
    p.stroke([(96, 110), (100, 122), (94, 130)], smooth=False, w=1.4, passes=1)
    p.specks(90, op=.45, r=(.6, 1.5), box=(44, 50, 160, 176))
    for x, y in ((48, 120), (150, 76), (70, 186), (136, 60)):
        p.dot(x, y, 2.6, color=GREEN, op=.8)
        p.dot(x + 4, y + 2, 1.6, color=GREEN, op=.8)


def mech(p):
    backdrop(p, '#7c6c3e')
    p.line(100, 46, 100, 14, w=3.0)
    p.shape(oval(100, 10, 6, 6, n=7), RED, w=2.2)
    bust(p, '#5c544a', neck=None)
    for k in range(4):
        p.stroke(arc(100, 176 + k * 8, 26, 6, 0, 180, n=5), w=2.4)
    brass, plate = '#a08e5c', '#b9a878'
    wolf_ears(p, brass, inner='#5c544a')
    for x, y in ((48, 34), (152, 34)):
        p.dot(x, y, 2.0)
    wolf_head(p, brass, plate)
    for a in ([(100, 50), (100, 102)], [(58, 76), (142, 76)], [(48, 126), (78, 132)], [(152, 126), (122, 132)]):
        p.line(a[0][0], a[0][1], a[1][0], a[1][1], w=1.8)
    for x, y in ((66, 62), (134, 62), (56, 116), (144, 116), (92, 58), (108, 58), (150, 138), (50, 138)):
        p.dot(x, y, 2.0)
    gear = star(76, 96, 19, 14, 9)
    p.shape(gear, '#5c544a', smooth=False, w=2.4)
    p.shape(oval(76, 96, 10, 10, n=9), GOLD, w=2.4)
    p.dot(76, 96, 3.2)
    slit = [(106, 92), (142, 86), (142, 98), (108, 102)]
    p.shape(slit, DARK, smooth=False, w=2.6)
    p.fill([(112, 94), (138, 90), (138, 95), (113, 99)], '#d9573f', smooth=False, jit=.4, shift=0)
    p.stroke([(146, 80), (126, 78), (104, 90)], w=4.0, over=2)
    p.shape([(88, 142), (112, 142), (106, 154), (100, 158), (94, 154)], DARK, w=2.2)
    grill = [(80, 162), (120, 162), (114, 176), (86, 176)]
    p.shape(grill, DARK, smooth=False, w=2.4)
    for x in range(86, 118, 6):
        p.line(x, 163, x, 175, w=1.6, color=BONE, passes=1)
    for sx in (-1, 1):
        p.shape(oval(100 + sx * 36, 150, 5, 5, n=7), STEEL, w=2.0)
        p.line(100 + sx * 33, 150, 100 + sx * 39, 150, w=1.2, passes=1)


ROLES = [('villager', villager), ('seer', seer), ('witch', witch), ('hunter', hunter), ('guard', guard),
         ('idiot', idiot), ('knight', knight), ('psychic', psychic), ('gravekeeper', gravekeeper),
         ('dreamer', dreamer), ('magician', magician), ('witcher', witcher), ('cupid', cupid), ('mixed', mixed),
         ('wolf', wolf), ('wolfking', wolfking), ('whitewolf', whitewolf), ('beauty', beauty),
         ('nightmare', nightmare), ('bloodmoon', bloodmoon), ('ghostrider', ghostrider), ('gargoyle', gargoyle),
         ('mech', mech)]


def render(name, fn, seed=7):
    p = Pen('%s-%d' % (name, seed))
    fn(p)
    return p.svg()
