import math
import sys
import time
import tkinter as tk

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

MESSAGE = "for you"
FONT_SIZE = 12
FPS = 60

RAMP = " .,:;-~=+*ox%#&@"
EXTRA = "♥*+·-|_✦"

SPEED = 1.5


def _beat(*ts):
    v = tuple(x / SPEED for x in ts)
    return v if len(v) > 1 else v[0]


T_SLIDE_IN = _beat(0.0, 1.9)
T_TYPE = _beat(1.4)
T_CUR_IN = _beat(2.5, 4.2)
T_CLICK = _beat(4.6)
T_DRAG = _beat(5.05, 6.5)
T_CUR_OUT = _beat(6.6, 7.4)
T_SLIDE = _beat(6.7, 8.1)
T_RISE = _beat(7.1, 9.9)
T_BLOOM = _beat(9.0, 11.9)
T_SHINE = _beat(10.9, 12.6)
T_HIDE = _beat(10.1, 11.9)
TYPE_STEP = 0.075 / SPEED

ENV_HW = 0.80
ENV_H = 0.88
ENV_Y0_START = -0.40
ENV_Y0_FINAL = 0.13
FLAP_DEPTH = 0.56 * ENV_H
HEART_SIZE = 0.15
ROSE_R = 0.36
ROSE_Y = -0.60
ROSE_GROW = 1.4
ROSE_Y_FINAL = -0.36
PIVOT_FINAL = 0.95
GOLDEN = math.pi * (3 - math.sqrt(5))

PAPER = np.array([1.00, 0.78, 0.70], np.float32)
PAPER_FLAP = np.array([1.00, 0.84, 0.76], np.float32)
LINING = np.array([0.70, 0.30, 0.40], np.float32)
INTERIOR = np.array([0.55, 0.20, 0.24], np.float32)
RAY_GOLD = np.array([1.00, 0.70, 0.30], np.float32)
WHITE = np.array([1.0, 1.0, 1.0], np.float32)
BLACK = np.array([0.0, 0.0, 0.0], np.float32)
ROSE_DARK = np.array([0.40, 0.00, 0.07], np.float32)
ROSE_MID = np.array([1.00, 0.08, 0.20], np.float32)
ROSE_LIGHT = np.array([1.00, 0.58, 0.62], np.float32)
LEAF_DARK = np.array([0.04, 0.30, 0.10], np.float32)
LEAF_LIGHT = np.array([0.45, 0.95, 0.40], np.float32)

CURSOR_PTS = [(0, 0), (0, 16), (3.8, 12.4), (6.6, 18.6), (9.0, 17.6), (6.3, 11.6), (11.4, 11.4)]


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def prog(t, a, b):
    return clamp01((t - a) / (b - a))


def smooth(x):
    return x * x * (3 - 2 * x)


def ease_out(x):
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def lerp(a, b, x):
    return a + (b - a) * x


def sstep(e0, e1, x):
    k = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return k * k * (3 - 2 * k)


def bezier(p0, p1, p2, p3, s):
    u = 1 - s
    return tuple(u ** 3 * a + 3 * u * u * s * b + 3 * u * s * s * c + s ** 3 * d
                 for a, b, c, d in zip(p0, p1, p2, p3))


def heartbeat(t):
    ph = t % 1.05
    return math.exp(-((ph - 0.15) / 0.06) ** 2) + 0.6 * math.exp(-((ph - 0.38) / 0.06) ** 2)


def sd_polygon(px, py, pts):
    d = (px - pts[0][0]) ** 2 + (py - pts[0][1]) ** 2
    s = np.ones_like(px)
    j = len(pts) - 1
    for i in range(len(pts)):
        ex, ey = pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]
        wx, wy = px - pts[i][0], py - pts[i][1]
        h = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0, 1)
        bx, by = wx - ex * h, wy - ey * h
        d = np.minimum(d, bx * bx + by * by)
        c1 = py >= pts[i][1]
        c2 = py < pts[j][1]
        c3 = ex * wy > ey * wx
        flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
        s = np.where(flip, -s, s)
        j = i
    return s * np.sqrt(d)


def load_font(size):
    for path, idx in [("/System/Library/Fonts/Menlo.ttc", 1), ("/System/Library/Fonts/Menlo.ttc", 0),
                      ("/System/Library/Fonts/Monaco.ttf", 0), ("DejaVuSansMono-Bold.ttf", 0),
                      ("DejaVuSansMono.ttf", 0), ("consolab.ttf", 0), ("consola.ttf", 0), ("cour.ttf", 0)]:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            pass
    sys.exit("No monospace TrueType font found (tried Menlo, DejaVu Sans Mono, Consolas, Courier).")


class Atlas:

    def __init__(self, size):
        font = load_font(size)
        asc, desc = font.getmetrics()
        self.cw = max(4, int(round(font.getlength("M"))))
        self.ch = asc + desc
        chars = []
        for c in RAMP + EXTRA + MESSAGE:
            if c not in chars:
                chars.append(c)
        self.index = {c: i for i, c in enumerate(chars)}
        self.n_ramp = len(RAMP)
        g = np.zeros((len(chars), self.ch, self.cw), np.float32)
        for i, c in enumerate(chars):
            im = Image.new("L", (self.cw, self.ch), 0)
            ImageDraw.Draw(im).text((0, 0), c, font=font, fill=255)
            g[i] = np.asarray(im, np.float32) / 255.0
        self.glyphs8 = (g * 255).astype(np.uint8)


class Scene:
    def __init__(self, W, H, atlas, seed=7):
        self.W, self.H, self.atlas = W, H, atlas
        cw, chh = atlas.cw, atlas.ch
        self.C, self.R = max(8, W // cw), max(8, H // chh)
        R, C = self.R, self.C
        self.ox, self.oy = (W - C * cw) // 2, (H - R * chh) // 2
        self.S = min(W / 2.0, H / 2.15)
        xs = ((np.arange(C) + 0.5) * cw + self.ox - W / 2) / self.S
        ys = ((np.arange(R) + 0.5) * chh + self.oy - H / 2) / self.S
        self.U = np.broadcast_to(xs[None, :], (R, C)).astype(np.float32)
        self.V = np.broadcast_to(ys[:, None], (R, C)).astype(np.float32)
        self.umax, self.vmax = W / 2 / self.S, H / 2 / self.S

        rng = np.random.default_rng(seed)
        self.noise_u = rng.random((R, C)).astype(np.float32)
        self.noise = self.noise_u - 0.5
        self.env_keep = np.ones((R, C), bool)
        self.env_none = np.zeros((R, C), bool)
        self.env_edge = self.env_none
        self.flick = rng.random((R, C)).astype(np.float32) * 6.283
        rows = np.arange(R)[:, None] / R
        self.reveal = ((0.15 + 1.25 * (0.55 * rng.random((R, C)) + 0.45 * rows)) / SPEED).astype(np.float32)
        self.scramble = rng.integers(5, atlas.n_ramp, (64, R, C))
        rr, cc = np.mgrid[0:R, 0:C]
        self.lining_pat = (rr % 4 == 1) & (((rr // 4) % 2 * 5 + cc) % 10 == 0)

        n = max(20, R * C // 85)
        self.stars = (rng.integers(0, R, n), rng.integers(0, C, n),
                      rng.random(n) * 6.283, 0.6 + rng.random(n) * 1.8)
        k = 52
        self.burst = list(zip(rng.uniform(0, 6.283, k), rng.uniform(0.25, 1.0, k),
                              rng.uniform(0.7, 1.6, k), rng.choice(list("♥♥*+·"), k), rng.random(k)))
        self.sparkles = list(zip(rng.uniform(1.1, 2.8, 40), rng.random(40)))
        self.floaters = list(zip(rng.uniform(0.42, 0.85, 14) * rng.choice([-1, 1], 14),
                                 rng.random(14), rng.uniform(3.5, 5.5, 14), rng.random(14) * 6.283))

    def paint(self, m, lum, col, reg=None):
        if reg is None:
            L, K, Q = self.lum, self.col, self.chr
        else:
            L, K, Q = self.lum[reg], self.col[reg], self.chr[reg]
        L[m] = lum[m] if np.ndim(lum) == 2 else lum
        K[m] = col[m] if np.ndim(col) == 3 else col
        Q[m] = -1

    def paint_env(self, m, lum, col):
        self.paint(m & self.env_keep, lum, col)
        edge = m & self.env_edge
        if edge.any():
            self.paint(edge, 0.95, np.array([1.0, 0.72, 0.5], np.float32))

    def region(self, x, y, rx, ry):
        r0, c0 = self.cell(x - rx, y - ry)
        r1, c1 = self.cell(x + rx, y + ry)
        r0, r1 = max(0, r0), min(self.R, r1 + 1)
        c0, c1 = max(0, c0), min(self.C, c1 + 1)
        if r0 >= r1 or c0 >= c1:
            return None
        return (slice(r0, r1), slice(c0, c1))

    def cell(self, x, y):
        c = int((x * self.S + self.W / 2 - self.ox) // self.atlas.cw)
        r = int((y * self.S + self.H / 2 - self.oy) // self.atlas.ch)
        return r, c

    def put(self, r, c, ch, col, lum=1.0):
        if 0 <= r < self.R and 0 <= c < self.C:
            self.chr[r, c] = self.atlas.index[ch]
            self.col[r, c] = col
            self.lum[r, c] = lum

    def draw_stars(self, t):
        r, c, ph, sp = self.stars
        fade = smooth(prog(t, 0.3, 2.2))
        b = (0.5 + 0.5 * np.sin(t * sp + ph)) ** 3 * 0.55 * fade
        for i in np.nonzero(b > 0.06)[0]:
            ch = "+" if b[i] > 0.42 else "·" if b[i] > 0.2 else "."
            self.put(r[i], c[i], ch, np.array([0.78, 0.62, 1.0]), float(b[i]))

    def draw_rays(self, t, hx, hy, amt, Rr=ROSE_R):
        if amt <= 0:
            return
        dx, dy = self.U - hx, self.V - hy
        r = np.sqrt(dx * dx + dy * dy)
        phi = np.arctan2(dy, dx)
        ray = (0.5 + 0.5 * np.cos(12 * phi + 0.35 * t)) ** 12 \
            + 0.7 * (0.5 + 0.5 * np.cos(7 * phi - 0.22 * t + 1.3)) ** 16
        fall = sstep(Rr * 0.95, Rr * 1.3, r) * np.exp(-(r - Rr) / 0.32)
        lum = 0.34 * ray * fall * amt
        self.paint(lum > 0.06, lum, RAY_GOLD)

    def draw_env_back(self, ey0, c):
        U, V = self.U, self.V
        au = np.abs(U) / ENV_HW
        inx = au <= 1
        if c < 0:
            k = -c
            tip = ey0 + FLAP_DEPTH * c
            line = ey0 + (tip - ey0) * (1 - au)
            m = inx & (V <= ey0) & (V >= line)
            depth = np.clip((ey0 - V) / (FLAP_DEPTH * k + 1e-6), 0, 1)
            lum = 0.08 + 0.08 * k + 0.06 * depth + 0.02 * self.noise
            edge = (V - line) < 0.03
            lum = np.where(edge, lum + 0.22, lum)
            self.paint_env(m, lum, LINING)
            if k > 0.35:
                rr, cc = np.nonzero(m & self.lining_pat & ~edge & self.env_keep)
                self.chr[rr, cc] = self.atlas.index["♥"]
                self.col[rr, cc] = (0.75, 0.12, 0.28)
                self.lum[rr, cc] = 0.45 * k
        ym = ey0 + 0.52 * ENV_H
        top_line = ey0 + (ym - ey0) * (1 - au)
        m = inx & (V >= ey0) & (V < top_line)
        depth = np.clip((V - ey0) / (ym - ey0), 0, 1)
        self.paint_env(m, 0.18 + 0.14 * (1 - depth), INTERIOR)

    def draw_env_front(self, ey0, c):
        U, V = self.U, self.V
        ey1 = ey0 + ENV_H
        ym = ey0 + 0.52 * ENV_H
        au = np.abs(U) / ENV_HW
        inx = au <= 1
        top_line = ey0 + (ym - ey0) * (1 - au)
        bot_line = ey1 - (ey1 - ym) * (1 - au)
        pocket = inx & (V >= top_line) & (V <= ey1)
        bottom = pocket & (V >= bot_line)
        side = pocket & ~bottom
        lum = np.where(bottom, 0.50 + 0.08 * (V - ym) / (ey1 - ym), np.where(U < 0, 0.30, 0.38))
        dsh = bot_line - V
        lum = np.where(side & (dsh < 0.06), lum * (0.45 + 0.55 * np.clip(dsh / 0.06, 0, 1)), lum)
        lum = np.where(bottom & (V - bot_line < 0.03), 0.78, lum)
        lum = np.where(pocket & (V - top_line < 0.03), 0.75, lum)
        border = np.minimum(np.minimum(ENV_HW - np.abs(U), V - ey0), ey1 - V)
        lum = np.where(border < 0.02, 0.72, lum)
        self.paint_env(pocket, lum + 0.03 * self.noise, PAPER)

        if c > 0:
            tip = ey0 + FLAP_DEPTH * c
            line = ey0 + (tip - ey0) * (1 - au)
            sh = pocket & (V > line) & (V - line < 0.06 * c) & self.env_keep
            self.lum = np.where(sh, self.lum * 0.45, self.lum)
            m = inx & (V >= ey0) & (V <= line)
            depth = np.clip((V - ey0) / (tip - ey0 + 1e-6), 0, 1)
            lum = 0.42 + 0.18 * c - 0.08 * depth
            lum = np.where((line - V) < 0.03, 0.8, lum)
            self.paint_env(m, lum + 0.03 * self.noise, PAPER_FLAP)

    def draw_heart(self, cx, cy, size, alpha):
        x = (self.U - cx) / size
        y = -(self.V - cy) / size + 0.12
        F = (x * x + y * y - 1) ** 3 - x * x * y ** 3
        xo, yo = x / 1.22, (y - 0.12) / 1.22 + 0.12
        ring = ((xo * xo + yo * yo - 1) ** 3 - xo * xo * yo ** 3 <= 0) & (F > 0)
        if alpha > 0.5:
            self.paint(ring, 0.0, BLACK)
        m = F <= 0
        hl = np.exp(-((x + 0.42) ** 2 + (y - 0.45) ** 2) / 0.12)
        depth = np.clip(-F * 4, 0, 1)
        lum = np.clip((0.62 + 0.3 * depth + 0.4 * hl) * alpha, 0, 1)
        col = np.array([0.98, 0.08, 0.22], np.float32) + (np.array([1, 0.65, 0.7], np.float32)
                                                           - np.array([0.98, 0.08, 0.22], np.float32)) * hl[..., None]
        self.paint(m, lum, col)

    def draw_text(self, t, ey0):
        spaced = " ".join(MESSAGE)
        n = len(spaced)
        r, c_mid = self.cell(0.0, ey0 + 0.80 * ENV_H)
        c0 = c_mid - n // 2
        lab = np.zeros((self.R, self.C), bool)
        lab[max(0, r - 1):r + 2, max(0, c0 - 2):max(0, c0 + n + 2)] = True
        self.paint(lab & self.env_keep, 0.0, BLACK)
        if t < T_TYPE:
            return
        shown = int((t - T_TYPE) / TYPE_STEP)
        for i, ch in enumerate(spaced[:shown]):
            if ch != " " and 0 <= r < self.R and 0 <= c0 + i < self.C and self.env_keep[r, c0 + i]:
                self.put(r, c0 + i, ch, np.array([1.0, 0.25, 0.4]), 1.0)
        if shown <= n + 8 and int(t * 4) % 2 == 0:
            self.put(r, c0 + min(shown, n), "_", np.array([1.0, 0.6, 0.7]), 1.0)

    def leaf(self, Ur, Vr, bx, by, theta, L, Wd, curl=0.3, reg=None):
        dx, dy = Ur - bx, Vr - by
        cs, sn = math.cos(theta), math.sin(theta)
        al = dx * cs + dy * sn
        ac = -dx * sn + dy * cs
        q = al / L
        ac = ac - curl * Wd * q * q
        hw = Wd * np.maximum(np.sin(np.pi * np.clip(q, 0, 1)), 0) ** 0.85 + 1e-6
        m = (q > 0) & (q < 1) & (np.abs(ac) < hw)
        side = ac / hw
        vein = np.abs(((q - np.abs(side) * 0.35) * 7) % 1 - 0.5) < 0.1
        lum = 0.45 + 0.28 * (side < 0) + 0.15 * (1 - np.abs(side))
        lum = np.where(np.abs(side) < 0.14, 0.22, lum) - 0.12 * vein
        lum = np.where(np.abs(side) > 0.86, 0.15, lum)
        col = LEAF_DARK + (LEAF_LIGHT - LEAF_DARK) * np.clip(lum, 0, 1)[..., None]
        self.paint(m, lum, col, reg)

    def draw_rose(self, t, px, pv, hv, bloom, grow, sway, shine, Rh=ROSE_R):
        k = Rh / ROSE_R
        ca, sa = math.cos(sway), math.sin(sway)
        du, dv = self.U - px, self.V - pv
        Ur = px + du * ca + dv * sa
        Vr = pv - du * sa + dv * ca
        length = pv - hv

        bend = 0.04 * k
        half = 0.042 * k
        s = (pv - Vr) / max(length, 1e-3)
        xs = px + bend * np.sin(np.pi * s)
        d = (Ur - xs) / half
        m = (s >= 0) & (s <= 1) & (np.abs(d) < 1)
        lum = 0.42 + 0.4 * (1 - d * d) - 0.18 * d
        lum = np.where(np.abs(d) > 0.75, 0.2, lum)
        self.paint(m, lum, LEAF_DARK + (LEAF_LIGHT - LEAF_DARK) * np.clip(lum, 0, 1)[..., None])
        for sl, sgn in ((0.28, -1), (0.47, 1), (0.66, -1)):
            tx = px + bend * math.sin(math.pi * sl) + sgn * half * 0.8
            ty = pv - sl * length
            sz = 0.05 * k * grow
            if sz > 0.005:
                pts = [(tx, ty - sz * 0.5), (tx + sgn * sz, ty - sz * 1.1), (tx, ty + sz * 0.5)]
                dd = sd_polygon(Ur, Vr, pts)
                self.paint(dd < 0, 0.45, np.array([0.35, 0.6, 0.2], np.float32))

        if grow > 0:
            for sl, th, flip in [(0.36, -0.35, 1), (0.58, math.pi + 0.4, -1)]:
                bx = px + bend * math.sin(math.pi * sl)
                by = pv - sl * length
                self.leaf(Ur, Vr, bx, by, th, 0.42 * k * grow, 0.13 * k * grow, 0.5 * flip)

        o = smooth(bloom)
        hx_s = px - sa * (hv - pv)
        hy_s = pv + ca * (hv - pv)
        reg = self.region(hx_s, hy_s, Rh * 1.25, Rh * 1.25)
        if reg is None:
            return
        Ur, Vr = Ur[reg], Vr[reg]
        x = (Ur - px) / Rh
        y = (Vr - hv) / Rh
        sweep = ((t * 0.3) % 1.0) * 3.6 - 1.8
        glint = np.exp(-(((x + y) * 0.707 - sweep) / 0.12) ** 2) * shine
        pulse = 1 + 0.10 * shine * (0.5 + 0.5 * math.sin(2 * math.pi * t / 2.4))
        pid = np.full(x.shape, -1, np.int32)
        order = [0]

        def ell(cx, cy, rx, ry, rot=0.0, ruffle=0.0):
            dx, dy = x - cx, y - cy
            c_, s_ = math.cos(rot), math.sin(rot)
            qx = (dx * c_ + dy * s_) / rx
            qy = (-dx * s_ + dy * c_) / ry
            e = qx * qx + qy * qy
            if ruffle:
                e = e * (1 + ruffle * np.sin(7 * np.arctan2(qy, qx) + cx * 9))
            return qx, qy, e

        def petal(m, lum, tone=1.0):
            if not m.any():
                return
            lum = np.clip((lum + 0.3 * glint) * pulse, 0, 1)
            lc = np.clip(lum * 1.25 * tone, 0, 1)[..., None]
            col = ROSE_DARK + (ROSE_MID - ROSE_DARK) * lc
            col = col + (ROSE_LIGHT - col) * np.clip((lum - 0.78) * 2.5, 0, 1)[..., None]
            self.paint(m, lum, col, reg)
            order[0] += 1
            pid[m] = order[0]

        for sgn in (-1, 1):
            qx, qy, e = ell(sgn * lerp(0.2, 0.68, o), lerp(-0.05, 0.14, o),
                            lerp(0.28, 0.46, o), 0.5, sgn * lerp(0.05, 0.7, o), 0.06 * o)
            lum = 0.6 + 0.2 * np.clip(0.4 - qy * 0.7, 0, 1)
            lum = lum + 0.35 * sstep(0.55, 0.8, np.sqrt(e)) * (qy < 0.3)
            petal(e < 1, lum, 0.9)
        for cx, cy, r in ((-0.46, -0.42, 0.42), (0.46, -0.42, 0.42), (0.0, -0.66, 0.5)):
            qx, qy, e = ell(cx * lerp(0.3, 1, o), lerp(-0.3, cy, o),
                            lerp(0.25, r * 1.15, o), lerp(0.25, r * 0.85, o), 0.0, 0.07 * o)
            lum = 0.58 + 0.18 * np.clip(-qy, 0, 1)
            lum = lum + 0.4 * sstep(0.55, 0.78, np.sqrt(e)) * (qy < 0.15)
            petal(e < 1, lum, 0.85)
        qx, qy, e = ell(0.0, lerp(-0.42, -0.46, o), lerp(0.3, 0.36, o), lerp(0.48, 0.3, o))
        r = np.sqrt(e)
        th = np.arctan2(qy, qx)
        f = (r * 2.6 - th / (2 * np.pi) + 10.0) % 1.0
        line = np.abs(f - 0.5) > 0.36
        lum = np.where(line, 0.12, 0.55 + 0.4 * r)
        petal(e < 1, lum, 1.0)
        cup_rx = lerp(0.34, 0.82, o)
        qx, qy, e = ell(0.0, lerp(-0.02, -0.08, o), cup_rx, 0.66)
        rim_y = lerp(-0.18, -0.3, o) + 0.07 * o * np.cos(x * 6.5) + 0.12 * (x / cup_rx) ** 2
        seam = 0.18 * lerp(0.4, 1, o) - 0.35 * (y - rim_y) * o
        nx = x / cup_rx
        body = (e < 1) & (y >= rim_y)
        shade = 0.55 + 0.3 * np.clip(1 - np.abs(nx + 0.3), 0, 1) - 0.15 * np.clip(qy, 0, 1)
        right = body & (x > seam)
        petal(right, shade * 0.9, 0.9)
        left = body & (x <= seam)
        petal(left, shade + 0.08, 1.0)
        lip = body & (y - rim_y < 0.11)
        petal(lip, np.full(x.shape, 0.97, np.float32), 1.1)

        P = np.pad(pid, 1, constant_values=-1)
        c = P[1:-1, 1:-1]
        edge = (c >= 0) & ((P[:-2, 1:-1] < c) | (P[2:, 1:-1] < c) | (P[1:-1, :-2] < c) | (P[1:-1, 2:] < c))
        L, K, Q = self.lum[reg], self.col[reg], self.chr[reg]
        L[edge] = 0.16
        K[edge] = (0.45, 0.02, 0.08)
        Q[edge] = -1

        sep_len = lerp(0.3, 0.45, o)
        for deg in (28, 75, 105, 152):
            self.leaf(Ur, Vr, px, hv + 0.5 * Rh, math.radians(deg), sep_len * Rh, 0.035 * k, 0.0, reg)

    def draw_sparkles(self, t, hx, hy, amt, Rr=ROSE_R):
        if amt <= 0:
            return
        varm_ratio = self.atlas.cw / self.atlas.ch
        for k, (P, ph) in enumerate(self.sparkles):
            pos = t / P + ph
            cyc = math.floor(pos)
            b = math.sin(math.pi * (pos - cyc)) ** 4 * amt
            if b < 0.08:
                continue
            rnd = np.random.default_rng(k * 7919 + cyc)
            ang = rnd.uniform(0, 6.283)
            rad = Rr * rnd.uniform(1.15, 2.2)
            r, c = self.cell(hx + rad * math.cos(ang), hy + rad * math.sin(ang) * 0.9)
            col = np.array([1.0, 0.93, 0.75])
            arm = int(round(b * 3.5))
            varm = int(round(arm * varm_ratio * 1.2))
            for j in range(1, arm + 1):
                self.put(r, c - j, "-", col, b * (1 - j / (arm + 1)))
                self.put(r, c + j, "-", col, b * (1 - j / (arm + 1)))
            for j in range(1, varm + 1):
                self.put(r - j, c, "|", col, b * (1 - j / (varm + 1)))
                self.put(r + j, c, "|", col, b * (1 - j / (varm + 1)))
            self.put(r, c, "✦" if b > 0.55 else "+" if b > 0.25 else "·", col, b)

    def draw_floaters(self, t, ey0, amt, base=None):
        if amt <= 0:
            return
        for x0, off, P, ph in self.floaters:
            local = ((t - T_SHINE[0]) / P + off) % 1.0
            a = math.sin(math.pi * local) * amt
            if a < 0.1:
                continue
            x = x0 + 0.06 * math.sin(6.283 * local * 1.3 + ph)
            y = (ey0 - 0.02 if base is None else base) - local * 1.3
            r, c = self.cell(x, y)
            self.put(r, c, "♥", np.array([1.0, 0.3 + 0.2 * math.sin(ph), 0.5]), a)

    def draw_burst(self, t, hx, hy):
        tau = t - (T_CLICK + 0.08)
        if tau <= 0 or tau > 1.8:
            return
        for ang, spd, life, ch, hue in self.burst:
            if tau > life:
                continue
            x = hx + math.cos(ang) * spd * tau
            y = hy + math.sin(ang) * spd * tau * 0.9 + 0.55 * tau * tau
            fade = 1 - tau / life
            col = np.array([1.0, 0.25 + 0.6 * hue, 0.4 + 0.2 * hue])
            self.put(*self.cell(x, y), ch, col, fade)

    def draw_ripple(self, t, cx, cy):
        dist = np.sqrt((self.U - cx) ** 2 + (self.V - cy) ** 2)
        for delay in (0.0, 0.12):
            tau = t - T_CLICK - delay
            if 0 < tau < 0.6:
                rad = 0.04 + 0.6 * ease_out(tau / 0.6)
                ring = np.exp(-((dist - rad) / 0.022) ** 2) * (1 - tau / 0.6)
                self.paint(ring > 0.25, ring, np.array([1.0, 0.8, 0.88], np.float32))

    def draw_cursor(self, x, y, scale):
        k = 0.023 * scale
        pts = [(x + px * k, y + py * k) for px, py in CURSOR_PTS]
        d = sd_polygon(self.U, self.V, pts)
        self.paint((d >= 0) & (d < 0.032), 0.0, BLACK)
        self.paint(d < 0, 0.85 + 0.15 * np.clip(-d / 0.03, 0, 1), WHITE)

    def render(self, t):
        R, C = self.R, self.C
        self.lum = np.zeros((R, C), np.float32)
        self.col = np.zeros((R, C, 3), np.float32)
        self.chr = np.full((R, C), -1, np.int32)

        hide = ease_in_out(prog(t, *T_HIDE))
        ey0 = lerp(ENV_Y0_START, ENV_Y0_FINAL, ease_in_out(prog(t, *T_SLIDE))) + 0.25 * hide
        th_ = hide * 1.1
        self.env_keep = self.noise_u >= th_
        self.env_edge = (self.noise_u < th_) & (self.noise_u > th_ - 0.08) if hide > 0 else self.env_none
        pd = prog(t, *T_DRAG)
        if t < T_DRAG[0]:
            c = 1.0
        elif pd < 1:
            c = math.cos(math.pi * ease_in_out(pd))
        else:
            tau = t - T_DRAG[1]
            c = -1 + 0.1 * math.exp(-5 * tau) * abs(math.sin(11 * tau))
        tip = ey0 + FLAP_DEPTH * c
        heart = (0.0, ey0 + FLAP_DEPTH - 0.07)

        rise = ease_in_out(prog(t, *T_RISE))
        px = 0.0
        pv = lerp(ey0 + 0.78, PIVOT_FINAL, hide)
        hv = lerp(lerp(ey0 + 0.62, ROSE_Y, rise), ROSE_Y_FINAL, hide)
        Rr = ROSE_R * lerp(1.0, ROSE_GROW, hide)
        bloom = prog(t, *T_BLOOM)
        shine = smooth(prog(t, *T_SHINE))
        grow = smooth(prog(t, T_RISE[0] + 1.0 / SPEED, T_RISE[1] + 0.6 / SPEED))
        sway = (0.035 * math.sin(6.283 * t / 4.2) + 0.012 * math.sin(6.283 * t / 1.7)) \
            * smooth(prog(t, T_RISE[1] - 0.8 / SPEED, T_RISE[1] + 1.5 / SPEED))
        hx_s = px - math.sin(sway) * (hv - pv)
        hy_s = pv + math.cos(sway) * (hv - pv)

        cursor = None
        target = (heart[0] + 0.03, heart[1] + 0.01)
        if T_CUR_IN[0] <= t <= T_CUR_OUT[1]:
            start = (self.umax + 0.2, target[1] + 0.9)
            press = 1 - 0.2 * math.exp(-((t - T_CLICK) / 0.07) ** 2)
            if t <= T_CUR_IN[1]:
                s = ease_in_out(prog(t, *T_CUR_IN))
                pos = bezier(start, (start[0] - 0.15, start[1] - 0.35),
                             (target[0] + 0.45, target[1] + 0.3), target, s)
            elif t < T_DRAG[0]:
                pos = target
            elif t <= T_DRAG[1] or t < T_CUR_OUT[0]:
                pos = (target[0] + 0.05 * math.sin(math.pi * pd), tip + (target[1] - (ey0 + FLAP_DEPTH)))
                press = 0.92 if t <= T_DRAG[1] else 1.0
            else:
                end = (target[0], ey0 - FLAP_DEPTH + (target[1] - (ey0 + FLAP_DEPTH)))
                s = prog(t, *T_CUR_OUT) ** 2
                pos = (lerp(end[0], self.umax + 0.3, s), lerp(end[1], end[1] - 0.25, s))
            cursor = (pos[0], pos[1], press)

        self.draw_stars(t)
        self.draw_rays(t, hx_s, hy_s, shine, Rr)
        self.draw_env_back(ey0, c)
        if t >= T_RISE[0]:
            self.draw_rose(t, px, pv, hv, bloom, grow, sway, shine, Rr)
        self.draw_env_front(ey0, c)
        self.draw_text(t, ey0)
        if t < T_CLICK + 0.25:
            hover = smooth(prog(t, T_CUR_IN[1] - 0.2, T_CUR_IN[1] + 0.15))
            pop = prog(t, T_CLICK + 0.05, T_CLICK + 0.25)
            size = HEART_SIZE * (1 + 0.08 * heartbeat(t) + 0.08 * hover) * (1 + 0.45 * pop)
            self.draw_heart(heart[0], heart[1], size, 1 - pop)
        self.draw_floaters(t, ey0, shine, lerp(ey0 - 0.02, pv, hide))
        self.draw_burst(t, *heart)
        self.draw_ripple(t, *target)
        self.draw_sparkles(t, hx_s, hy_s, shine, Rr)
        if cursor:
            self.draw_cursor(*cursor)

        self.lum = self.lum + np.where(self.lum > 0.05, 0.035 * np.sin(t * 3.1 + self.flick), 0)

        if t < T_SLIDE_IN[1] + 0.4 / SPEED:
            occ = (self.lum > 0.03) | (self.chr >= 0)
            hidden = occ & (t < self.reveal - 0.3)
            scr = occ & (t >= self.reveal - 0.3) & (t < self.reveal)
            self.lum[hidden] = 0
            self.chr[hidden] = -1
            self.chr[scr] = self.scramble[int(t * 24) % 64][scr]
            self.col[scr] = (1.0, 0.95, 0.95)
            self.lum[scr] = 0.9

        bloom_amt = 0.45 + 0.35 * shine * (0.6 + 0.4 * math.sin(6.283 * t / 2.4))
        return self.compose(bloom_amt)

    def compose(self, bloom_amt):
        a = self.atlas
        R, C, ch, cw, W, H = self.R, self.C, a.ch, a.cw, self.W, self.H
        lum = np.clip(self.lum, 0, 1)
        idx = np.clip((lum * (a.n_ramp - 1) + 0.5).astype(np.int32), 0, a.n_ramp - 1)
        idx = np.where(self.chr >= 0, self.chr, idx)
        rgb = np.clip(self.col * (0.3 + 0.7 * lum)[..., None] * 1.15 * 255, 0, 255).astype(np.uint8)
        mask = Image.fromarray(np.ascontiguousarray(
            a.glyphs8[idx].transpose(0, 2, 1, 3).reshape(R * ch, C * cw)))
        color = Image.fromarray(rgb).resize((C * cw, R * ch), Image.NEAREST)
        text = ImageChops.multiply(color, Image.merge("RGB", (mask, mask, mask)))
        base = Image.new("RGB", (W, H))
        base.paste(text, (self.ox, self.oy))
        sw, sh = max(1, W // 4), max(1, H // 4)
        g1 = base.resize((sw, sh), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.5))
        g2 = base.resize((max(1, W // 12), max(1, H // 12)), Image.BILINEAR) \
            .filter(ImageFilter.GaussianBlur(2.5)).resize((sw, sh), Image.BILINEAR)
        k1, k2 = 0.8 * bloom_amt, 1.5 * bloom_amt
        glow = ImageChops.add(g1.point(lambda v: min(255, int(v * k1))),
                              g2.point(lambda v: min(255, int(v * k2))))
        return ImageChops.add(base, glow.resize((W, H), Image.BILINEAR))


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("for you ♥")
        self.root.configure(bg="black")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        H = min(980, int(sh * 0.88))
        W = min(int(H * 0.86), sw)
        self.root.geometry("%dx%d+%d+%d" % (W, H, (sw - W) // 2, max(0, (sh - H) // 2 - 20)))
        self.label = tk.Label(self.root, bg="black", bd=0, highlightthickness=0)
        self.label.pack(fill="both", expand=True)
        self.atlas = Atlas(FONT_SIZE)
        self.scene = Scene(W, H, self.atlas)
        self.photo = None
        self.pending = None
        self.fullscreen = False
        for key in ("<space>", "r", "R"):
            self.root.bind(key, lambda e: self.restart())
        for key in ("<Escape>", "q", "Q"):
            self.root.bind(key, lambda e: self.root.destroy())
        self.root.bind("f", self.toggle_fullscreen)
        self.root.bind("F", self.toggle_fullscreen)
        self.root.bind("<Configure>", self.on_configure)
        self.t0 = time.perf_counter()
        self.root.after(50, self.tick)
        self.root.mainloop()

    def restart(self):
        self.t0 = time.perf_counter()

    def toggle_fullscreen(self, _=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def on_configure(self, e):
        if e.widget is not self.root or e.width < 300 or e.height < 300:
            return
        if abs(e.width - self.scene.W) > 4 or abs(e.height - self.scene.H) > 4:
            if self.pending:
                self.root.after_cancel(self.pending)
            self.pending = self.root.after(200, self.rebuild)

    def rebuild(self):
        self.pending = None
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w < 300 or h < 300 or (abs(w - self.scene.W) <= 4 and abs(h - self.scene.H) <= 4):
            return
        self.scene = Scene(w, h, self.atlas)
        self.photo = None

    def tick(self):
        start = time.perf_counter()
        img = self.scene.render(start - self.t0)
        if self.photo is None or self.photo.width() != img.width or self.photo.height() != img.height:
            self.photo = ImageTk.PhotoImage(img)
            self.label.configure(image=self.photo)
        else:
            self.photo.paste(img)
        spent = (time.perf_counter() - start) * 1000
        self.root.after(max(1, int(1000 / FPS - spent)), self.tick)


def snapshots(times, W=840, H=980):
    sc = Scene(W, H, Atlas(FONT_SIZE))
    for t in times:
        t0 = time.perf_counter()
        sc.render(t).save("snap_%05.2f.png" % t)
        print("t=%.2f  %.0f ms" % (t, (time.perf_counter() - t0) * 1000))


if __name__ == "__main__":
    if tk.TkVersion < 8.6:
        import os
        venv_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
        if os.path.exists(venv_py) and os.path.realpath(sys.executable) != os.path.realpath(venv_py):
            os.execv(venv_py, [venv_py] + sys.argv)
        sys.exit("This Python has Tk %s, which draws a blank window on macOS. Run it with a Python "
                 "that has Tk 8.6+ (e.g. Homebrew python3.14 with numpy + pillow)." % tk.TkVersion)
    if len(sys.argv) > 2 and sys.argv[1] == "--snap":
        snapshots([float(x) for x in sys.argv[2].split(",")])
    else:
        App()
