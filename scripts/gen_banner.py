#!/usr/bin/env python3
"""Generate image/banner.svg: a field of flickering 0 and 1 where the 2s spell phrases in turn.

Transparent background, green only. Run: python3 scripts/gen_banner.py
"""
import random
from pathlib import Path

# (lines, (scale_x, scale_y)): each phrase is drawn with 2s and held, then the field scrambles again
PHRASES = [
    (["Hello, world!"], (1, 1)),
]
SCRAMBLE, HOLD = 1.0, 2.0  # seconds per phrase (3 s loop)
WIDTH, HEIGHT = 656, 121  # fixed size of the image
COLS, ROWS = 80, 10  # 80 columns, like a classic terminal line; 2 empty rows above the text, 2 below the baseline
TOP_PAD = 2  # empty rows above the text
PITCH_X, PITCH_Y = WIDTH / COLS, HEIGHT / ROWS
DIM = 1  # opacity of the background digits (their color is already dim)
FLICKER_SHARE = 0.4  # share of cells that flicker while scrambling
VARIANTS = 10  # distinct flicker speeds/phases

# 5x7 pixel font, only the glyphs we need
FONT = {
    "H": ["X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "e": [".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXX."],
    "l": ["XX...", ".X...", ".X...", ".X...", ".X...", "XXX.."],
    "o": [".....", ".XXX.", "X...X", "X...X", "X...X", ".XXX."],
    ",": [".....", ".....", ".....", ".....", ".XX..", ".XX..", ".X..."],
    "w": [".....", "X...X", "X...X", "X.X.X", "XX.XX", "X...X"],
    "r": [".....", "X.XX.", "XX..X", "X....", "X....", "X...."],
    "d": ["....X", ".XXXX", "X...X", "X...X", "X...X", ".XXXX"],
    "!": ["..X..", "..X..", "..X..", "..X..", ".....", "..X.."],
    "3": ["XXXX.", "....X", "....X", ".XXX.", "....X", "....X", "XXXX."],
    "0": [".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."],
    "1": ["..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
    "4": ["...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."],
    "2": [".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"],
}
GLYPH_W, GLYPH_H = 5, 7  # 6 rows of letters plus one row below the baseline for the comma
SPACE_W = 5  # width of a space, in cells
LETTER_GAP = 1  # blank cells between letters


def glyph(ch):
    """Rows of one glyph, trimmed to its ink columns, so spacing looks even."""
    if ch == " ":
        return ["." * SPACE_W] * GLYPH_H
    rows = FONT[ch] + ["." * GLYPH_W] * (GLYPH_H - len(FONT[ch]))
    inked = [i for i in range(GLYPH_W) if any(row[i] == "X" for row in rows)]
    return [row[inked[0]:inked[-1] + 1] for row in rows]


def mask_for(lines, scale):
    """Set of (col, row) cells that hold a 2, centered in the grid by their ink."""
    sx, sy = scale
    cells = set()
    line_cells = []
    for li, line in enumerate(lines):
        x = 0
        for ch in line:
            rows = glyph(ch)
            for r, row in enumerate(rows):
                for c, mark in enumerate(row):
                    if mark == "X":
                        line_cells.append((x + c, li * (GLYPH_H + 1) + r))
            x += len(rows[0]) + LETTER_GAP
    min_x = min(c for c, _ in line_cells)
    max_x = max(c for c, _ in line_cells)
    min_y = min(r for _, r in line_cells)
    max_y = max(r for _, r in line_cells)
    width, height = (max_x - min_x + 1) * sx, (max_y - min_y + 1) * sy
    left, top = (COLS - width) // 2, TOP_PAD
    for c, r in line_cells:
        for dy in range(sy):
            for dx in range(sx):
                cells.add((left + (c - min_x) * sx + dx, top + (r - min_y) * sy + dy))
    return cells


masks = [mask_for(lines, scale) for lines, scale in PHRASES]
N = len(PHRASES)
T = SCRAMBLE + HOLD
CYCLE = T * N

# Segment 2k is the scramble of phrase k, segment 2k+1 is its hold.
EPS = 0.01


def keyframes(name, opacity_of_segment, hide_when_zero=False):
    frames = []
    for seg in range(2 * N):
        start = (seg // 2) * T + (0 if seg % 2 == 0 else SCRAMBLE)
        end = start + (SCRAMBLE if seg % 2 == 0 else HOLD)
        value = opacity_of_segment(seg)
        # visibility:hidden lets the browser skip painting (and the animations inside) while the layer is off
        extra = f";visibility:{'visible' if value else 'hidden'}" if hide_when_zero else ""
        frames.append(f"{start / CYCLE * 100:.2f}%{{opacity:{value}{extra}}}")
        frames.append(f"{end / CYCLE * 100 - EPS:.2f}%{{opacity:{value}{extra}}}")
    return f"@keyframes {name}{{{''.join(frames)}}}"


def in_hold(seg):
    return seg % 2 == 1


rng = random.Random(8)  # fixed seed: the output is reproducible
cells, used = [], set()
flips = {v: ([], []) for v in range(VARIANTS)}  # per flicker variant: (zeros, ones)
for r in range(ROWS):
    for c in range(COLS):
        x, y = f"{c * PITCH_X + PITCH_X / 2:.1f}", f"{r * PITCH_Y + PITCH_Y - 2.5:.1f}"
        m = sum(1 << k for k, mask in enumerate(masks) if (c, r) in mask)
        flick = rng.random() < FLICKER_SHARE
        used.add((m, flick))
        bit = rng.choice("01")
        v = rng.randrange(VARIANTS)
        if flick:
            flips[v][0].append(f'<text x="{x}" y="{y}">0</text>')
            flips[v][1].append(f'<text x="{x}" y="{y}">1</text>')
        cells.append(f'<text class="n{m}{"f" if flick else ""}" x="{x}" y="{y}">{bit}</text>')
        if m:
            cells.append(f'<text class="t{m}" x="{x}" y="{y}">2</text>')

css, anim = [], []
for m, flick in sorted(used):
    name = f"n{m}{'f' if flick else ''}"
    first_has_2 = m & 1
    # static fallback (reduced motion) shows the first phrase
    css.append(f".{name}{{opacity:{0 if first_has_2 else DIM}}}")
    if flick:
        fn = lambda seg, m=m: DIM if in_hold(seg) and not (m >> (seg // 2)) & 1 else 0
    else:
        fn = lambda seg, m=m: 0 if in_hold(seg) and (m >> (seg // 2)) & 1 else DIM
    anim.append(f".{name}{{animation:{name} {CYCLE}s linear infinite}}")
    anim.append(keyframes(name, fn))
for m in sorted({m for m, _ in used if m}):
    css.append(f".t{m}{{opacity:{1 if m & 1 else 0}}}")
    anim.append(f".t{m}{{animation:t{m} {CYCLE}s linear infinite}}")
    anim.append(keyframes(f"t{m}", lambda seg, m=m: 1 if in_hold(seg) and (m >> (seg // 2)) & 1 else 0))
css.append(".gate{opacity:0;visibility:hidden}")
anim.append(f".gate{{animation:gate {CYCLE}s linear infinite}}")
anim.append(keyframes("gate", lambda seg: 0 if in_hold(seg) else 1, hide_when_zero=True))
anim.append(".a,.b{animation-timing-function:steps(1,end);animation-iteration-count:infinite}")
for i in range(VARIANTS):
    p = rng.uniform(0.28, 0.7)
    d = -rng.uniform(0, p)
    anim.append(f".v{i}{{animation-duration:{p:.2f}s;animation-delay:{d:.2f}s}}")
anim.append(".a{animation-name:flip0}.b{animation-name:flip1}")
anim.append("@keyframes flip0{0%{opacity:1}50%{opacity:0}100%{opacity:1}}")
anim.append("@keyframes flip1{0%{opacity:0}50%{opacity:1}100%{opacity:0}}")

width, height = WIDTH, HEIGHT
# one animated <g> per variant and digit: all cells of a variant flip in unison, so ~20 animations instead of one per cell
flip_groups = "".join(
    f'<g class="a v{v}">{"".join(z)}</g><g class="b v{v}">{"".join(o)}</g>' for v, (z, o) in flips.items()
)
words = ", ".join(" ".join(lines) for lines, _ in PHRASES)
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="t d">
<title id="t">Phrases written with the digit 2</title>
<desc id="d">A field of flickering zeros and ones. The digits settle, and the twos spell "{words}". Then it repeats.</desc>
<style>
:root{{--ok:#79cf71;--dim:#16391a}}
@media (prefers-color-scheme:light){{:root{{--ok:#216e39;--dim:#9be9a8}}}}
text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:9px;text-anchor:middle;fill:var(--dim)}}
[class^=t]{{font-weight:700;font-size:11px;fill:var(--ok)}}
{"".join(css)}
@media (prefers-reduced-motion:no-preference){{
{"".join(anim)}
}}
</style>
<g class="gate" aria-hidden="true">{flip_groups}</g>
<g>{"".join(cells)}</g>
</svg>
"""
out = Path(__file__).parent.parent / "image" / "banner.svg"
out.write_text(svg, encoding="utf-8")
print(out, len(svg), "bytes", f"{width}x{height}", len(used), "pattern classes")
