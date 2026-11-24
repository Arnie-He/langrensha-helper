# -*- coding: utf-8 -*-
"""手绘线条：把几何形状画成抖动的、来回描两遍的墨线，输出 SVG。

所有素材都用这支「笔」画：轮廓线描两遍、粗细不匀、端点略微出头；
颜色是平涂的色块，故意和轮廓错开一点；暗部用排线。只用标准库。
"""
import math
import random

INK = '#1c1712'
PAPER = '#d9caa5'
BONE = '#ece2c6'


def f(x):
    s = '%.1f' % x
    return s[:-2] if s.endswith('.0') else s


def mir(pts, cx=100.0):
    """左右镜像（并反转顺序，保持绕向）。"""
    return [(2 * cx - x, y) for x, y in reversed(pts)]


def oval(cx, cy, rx, ry=None, n=12, rot=0.0):
    ry = rx if ry is None else ry
    r = math.radians(rot)
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r)))
    return out


def arc(cx, cy, rx, ry, a0, a1, n=8):
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / float(n))
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


def star(cx, cy, r1, r2, n, rot=-90.0):
    out = []
    for i in range(n * 2):
        a = math.radians(rot + 180.0 * i / n)
        r = r1 if i % 2 == 0 else r2
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def sample(pts, closed, k=5):
    """把过这些点的平滑曲线取成密一些的折线（给排线裁剪用）。"""
    n = len(pts)
    if n < 3:
        return list(pts)

    def P(i):
        return pts[i % n] if closed else pts[max(0, min(n - 1, i))]
    out = []
    for i in range(n if closed else n - 1):
        p0, p1, p2, p3 = P(i - 1), P(i), P(i + 1), P(i + 2)
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        for s in range(k):
            t = s / float(k)
            u = 1 - t
            out.append((u ** 3 * p1[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p2[0],
                        u ** 3 * p1[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p2[1]))
    if not closed:
        out.append(pts[-1])
    return out


class Pen(object):
    def __init__(self, seed, w=200, h=200):
        self.rnd = random.Random(seed)
        self.w, self.h = w, h
        self.items = []

    # ---------------------------------------------------------------- 基础

    def j(self, a):
        return self.rnd.uniform(-a, a) if a else 0.0

    def wob(self, pts, a):
        return [(x + self.j(a), y + self.j(a)) for x, y in pts]

    def d_smooth(self, pts, closed):
        n = len(pts)
        if n < 3:
            return self.d_sharp(pts, closed)

        def P(i):
            return pts[i % n] if closed else pts[max(0, min(n - 1, i))]
        d = ['M%s %s' % (f(pts[0][0]), f(pts[0][1]))]
        for i in range(n if closed else n - 1):
            p0, p1, p2, p3 = P(i - 1), P(i), P(i + 1), P(i + 2)
            d.append('C%s %s %s %s %s %s' % (
                f(p1[0] + (p2[0] - p0[0]) / 6.0), f(p1[1] + (p2[1] - p0[1]) / 6.0),
                f(p2[0] - (p3[0] - p1[0]) / 6.0), f(p2[1] - (p3[1] - p1[1]) / 6.0),
                f(p2[0]), f(p2[1])))
        if closed:
            d.append('Z')
        return ''.join(d)

    def d_sharp(self, pts, closed, bow=0.0):
        d = ['M%s %s' % (f(pts[0][0]), f(pts[0][1]))]
        seq = list(pts[1:]) + ([pts[0]] if closed else [])
        prev = pts[0]
        for p in seq:
            if bow:
                mx, my = (prev[0] + p[0]) / 2.0, (prev[1] + p[1]) / 2.0
                dx, dy = p[0] - prev[0], p[1] - prev[1]
                ln = math.hypot(dx, dy) or 1.0
                k = self.j(bow) * min(1.0, ln / 40.0)
                d.append('Q%s %s %s %s' % (f(mx - dy / ln * k), f(my + dx / ln * k), f(p[0]), f(p[1])))
            else:
                d.append('L%s %s' % (f(p[0]), f(p[1])))
            prev = p
        if closed:
            d.append('Z')
        return ''.join(d)

    def _add(self, d, fill=None, stroke=None, w=None, op=1.0):
        a = ['<path d="%s"' % d, ' fill="%s"' % (fill or 'none')]
        if stroke:
            a.append(' stroke="%s" stroke-width="%s"' % (stroke, f(w)))
        if op < 1:
            a.append(' opacity="%s"' % ('%.2f' % op).rstrip('0'))
        a.append('/>')
        self.items.append(''.join(a))

    # ---------------------------------------------------------------- 画

    def stroke(self, pts, closed=False, w=2.6, color=INK, smooth=True, jit=1.0, passes=2, op=1.0, over=0.0):
        """描线。passes=2 时第二遍更细、更歪，像来回描了一下。over 是两端出头的长度。"""
        for k in range(passes):
            q = self.wob(pts, jit * (1.0 if k == 0 else 1.5))
            if over and not closed and len(q) >= 2:
                q = list(q)
                for a, b in ((0, 1), (-1, -2)):
                    dx, dy = q[a][0] - q[b][0], q[a][1] - q[b][1]
                    ln = math.hypot(dx, dy) or 1.0
                    e = over * self.rnd.uniform(.3, 1.2)
                    q[a] = (q[a][0] + dx / ln * e, q[a][1] + dy / ln * e)
            d = self.d_smooth(q, closed) if smooth else self.d_sharp(q, closed, bow=2.0)
            self._add(d, None, color, w * (1.0 if k == 0 else self.rnd.uniform(.4, .7)), op)

    def fill(self, pts, color, smooth=True, jit=1.2, op=1.0, shift=1.4):
        dx, dy = self.j(shift), self.j(shift)
        q = [(x + dx + self.j(jit), y + dy + self.j(jit)) for x, y in pts]
        self._add(self.d_smooth(q, True) if smooth else self.d_sharp(q, True), color, None, None, op)

    def shape(self, pts, fill=None, w=2.6, smooth=True, color=INK, jit=1.0, passes=2, shift=1.4):
        if fill:
            self.fill(pts, fill, smooth=smooth, shift=shift)
        self.stroke(pts, closed=True, w=w, color=color, smooth=smooth, jit=jit, passes=passes)

    def line(self, x1, y1, x2, y2, w=2.0, color=INK, jit=.8, passes=2, op=1.0, over=0.0):
        mx, my = (x1 + x2) / 2.0 + self.j(1.5), (y1 + y2) / 2.0 + self.j(1.5)
        self.stroke([(x1, y1), (mx, my), (x2, y2)], w=w, color=color, jit=jit, passes=passes, op=op, over=over)

    def dot(self, x, y, r, color=INK, op=1.0):
        self.fill(oval(x, y, r, r * self.rnd.uniform(.85, 1.15), n=7), color, jit=r * .12, op=op, shift=0)

    def hatch(self, pts, angle=40.0, gap=5.0, w=1.0, color=INK, op=.55, jit=.7, skip=.06, smooth=True, cross=False):
        """排线：在多边形里画一组平行的短线。"""
        poly = sample(pts, True) if smooth else list(pts)
        for ang in ([angle, angle + 82] if cross else [angle]):
            a = math.radians(ang)
            ca, sa = math.cos(a), math.sin(a)
            rot = [(x * ca + y * sa, -x * sa + y * ca) for x, y in poly]
            ys = [p[1] for p in rot]
            y, top, n, d = min(ys) + gap * self.rnd.uniform(.3, .9), max(ys), len(rot), []
            while y < top:
                xs = []
                for i in range(n):
                    (x1, y1), (x2, y2) = rot[i], rot[(i + 1) % n]
                    if (y1 <= y < y2) or (y2 <= y < y1):
                        xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
                xs.sort()
                for k in range(0, len(xs) - 1, 2):
                    xa, xb = xs[k] + self.rnd.uniform(0, 2.0), xs[k + 1] - self.rnd.uniform(0, 2.0)
                    if xb - xa < 2 or self.rnd.random() < skip:
                        continue
                    ya, yb = y + self.j(jit), y + self.j(jit)
                    d.append('M%s %sL%s %s' % (f(xa * ca - ya * sa), f(xa * sa + ya * ca),
                                               f(xb * ca - yb * sa), f(xb * sa + yb * ca)))
                y += gap * self.rnd.uniform(.7, 1.3)
            if d:
                self._add(''.join(d), None, color, w, op)

    def specks(self, n, color=INK, op=.35, r=(.5, 1.3), box=None):
        """纸上的墨点。"""
        x0, y0, x1, y1 = box or (0, 0, self.w, self.h)
        d = []
        for _ in range(n):
            x, y, rr = self.rnd.uniform(x0, x1), self.rnd.uniform(y0, y1), self.rnd.uniform(*r)
            d.append('M%s %sh%s' % (f(x), f(y), f(rr)))
        self._add(''.join(d), None, color, 1.4, op)

    def raw(self, s):
        self.items.append(s)

    def svg(self, extra=''):
        # 必须写明宽高：border-image 的九宫格切片是按图片的固有尺寸算的
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s"%s>'
                '<g stroke-linecap="round" stroke-linejoin="round">%s</g></svg>'
                % (f(self.w), f(self.h), f(self.w), f(self.h), extra, ''.join(self.items)))
