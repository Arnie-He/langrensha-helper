# -*- coding: utf-8 -*-
"""极简二维码生成器（只用标准库）。

只实现本项目需要的部分：字节模式、纠错等级 L、版本 1-6（最多 134 字节），
足够放下一条带房间号的网址。
"""

# 版本 -> (每块纠错码字数, 块数, 总码字数)   —— 纠错等级 L
_VERSIONS = {
    1: (7, 1, 26), 2: (10, 1, 44), 3: (15, 1, 70),
    4: (20, 1, 100), 5: (26, 1, 134), 6: (18, 2, 172),
}

_MASKS = [
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
]


def _mul(x, y):
    """GF(2^8) 乘法，本原多项式 0x11D。"""
    z = 0
    for i in range(7, -1, -1):
        z = ((z << 1) ^ ((z >> 7) * 0x11D)) & 0xFF
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _mul(coef, factor)
    return result


def _codewords(data):
    for ver in sorted(_VERSIONS):
        ecl, nblk, total = _VERSIONS[ver]
        cap = total - ecl * nblk
        if len(data) + 2 <= cap:
            break
    else:
        raise ValueError('内容太长，放不进二维码')

    bits = []

    def put(val, n):
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))

    put(4, 4)                      # 字节模式
    put(len(data), 8)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    put(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < cap * 8:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11

    words = [int(''.join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    size = cap // nblk
    div = _rs_divisor(ecl)
    blocks = [words[i * size:(i + 1) * size] for i in range(nblk)]
    eccs = [_rs_remainder(b, div) for b in blocks]
    out = []
    for i in range(size):
        out += [b[i] for b in blocks]
    for i in range(ecl):
        out += [e[i] for e in eccs]
    return ver, out


def _penalty(m):
    size = len(m)
    score = 0
    lines = [row[:] for row in m] + [[m[y][x] for y in range(size)] for x in range(size)]
    for line in lines:
        run, prev = 0, None
        for v in line:
            if v == prev:
                run += 1
                if run == 5:
                    score += 3
                elif run > 5:
                    score += 1
            else:
                run, prev = 1, v
        s = ''.join('1' if v else '0' for v in line)
        score += 40 * (s.count('10111010000') + s.count('00001011101'))
    for y in range(size - 1):
        for x in range(size - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(sum(1 for v in row if v) for row in m)
    total = size * size
    score += 10 * (abs(dark * 20 - total * 10) // total)
    return score


def matrix(text):
    """返回二维布尔矩阵，True 为黑色模块。"""
    ver, words = _codewords(text.encode('utf-8'))
    size = ver * 4 + 17
    m = [[False] * size for _ in range(size)]
    fn = [[False] * size for _ in range(size)]

    def setf(x, y, dark):
        m[y][x] = dark
        fn[y][x] = True

    for i in range(size):                               # 定时图案
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):   # 三个定位角
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    dist = max(abs(dx), abs(dy))
                    setf(x, y, dist != 2 and dist != 4)
    if ver >= 2:                                        # 校正图案
        c = size - 7
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                setf(c + dx, c + dy, max(abs(dx), abs(dy)) != 1)

    def draw_format(mask):
        data = (1 << 3) | mask                          # 纠错等级 L = 01
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = ((data << 10) | rem) ^ 0x5412

        def bit(i):
            return (bits >> i) & 1 != 0
        for i in range(0, 6):
            setf(8, i, bit(i))
        setf(8, 7, bit(6))
        setf(8, 8, bit(7))
        setf(7, 8, bit(8))
        for i in range(9, 15):
            setf(14 - i, 8, bit(i))
        for i in range(0, 8):
            setf(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            setf(8, size - 15 + i, bit(i))
        setf(8, size - 8, True)

    draw_format(0)                                      # 先占位

    i = 0
    nbits = len(words) * 8
    right = size - 1
    while right >= 1:                                   # 之字形填数据
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = size - 1 - vert if upward else vert
                if not fn[y][x] and i < nbits:
                    m[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 != 0
                    i += 1
        right -= 2

    def apply_mask(k):
        f = _MASKS[k]
        for y in range(size):
            for x in range(size):
                if not fn[y][x] and f(x, y):
                    m[y][x] = not m[y][x]

    best, best_score = 0, None
    for k in range(8):                                  # 选最容易识别的掩码
        apply_mask(k)
        draw_format(k)
        score = _penalty(m)
        if best_score is None or score < best_score:
            best, best_score = k, score
        apply_mask(k)
    apply_mask(best)
    draw_format(best)
    return m


def svg(text, quiet=4):
    m = matrix(text)
    size = len(m)
    full = size + quiet * 2
    path = []
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                path.append('M%d %dh1v1h-1z' % (x + quiet, y + quiet))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'shape-rendering="crispEdges"><rect width="%d" height="%d" fill="#fff"/>'
            '<path d="%s" fill="#000"/></svg>') % (full, full, full, full, ''.join(path))
