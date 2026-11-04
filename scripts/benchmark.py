#!/usr/bin/env python3
"""Benchmark the banner and check it against the acceptance criteria (see "For Agents" in README.md).

  python3 scripts/benchmark.py old.svg new.svg            size and structure (no dependencies)
  python3 scripts/benchmark.py --cpu old.svg new.svg      + CPU time in Chrome   (pip install playwright, Chrome)
  python3 scripts/benchmark.py --check old.svg new.svg    + acceptance criteria  (pip install playwright pillow, Chrome)

The first file is the reference (the current banner). Every other file is compared with it.
Without arguments the current image/banner.svg is measured alone.
Files from pull requests are untrusted: the banner is only ever opened in the browser, never executed here.
"""
import argparse
import base64
import gzip
import io
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT = Path(__file__).parent.parent / "image" / "banner.svg"

# Acceptance criteria. Keep in sync with the table in README.md.
SPEC = {
    "width": 656,
    "height": 121,
    "grid": (80, 10),  # columns, rows of digits; used only to look at the picture cell by cell
    "loop": 3.0,  # seconds for the whole animation
    "scramble": 1.0,  # the first second of a loop flickers, the other 2 seconds are a still "Hello, world!"
    "margin": 0.1,  # seconds of tolerance around the border between the two phases
    "min_share": 0.30,  # at least this share of the cells must flicker while scrambling
    "rate": (2.0, 8.0),  # median toggles per second of a flickering cell
    "match": 0.90,  # overlap (IoU) of the bright "2" pixels with the reference text
    "ok_color": {"light": (0x21, 0x6E, 0x39), "dark": (0x79, 0xCF, 0x71)},  # color of the 2s per theme
    "color_distance": 60,
    "cpu_gain": 0.05,  # a new banner must use at least 5% less CPU ...
    "size_gain": 0.10,  # ... or be at least 10% smaller (gzip) at the same CPU (within 5%)
}


# ---------- static metrics (stdlib only) ----------

def read_svg(path):
    raw = path.read_bytes()
    # untrusted input: the stdlib XML parser is open to entity-expansion attacks and a banner needs no DOCTYPE
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        sys.exit(f"{path}: DOCTYPE and ENTITY declarations are not allowed in the banner")
    return raw, ET.fromstring(raw)


def static_metrics(path):
    raw, root = read_svg(path)
    css = " ".join(el.text or "" for el in root.iter() if el.tag.endswith("style"))
    animated = set()
    for selectors, body in re.findall(r"([^{}@]+)\{([^{}]*animation[^{}]*)\}", css):
        if "animation-name" in body or re.search(r"animation\s*:", body):
            animated.update(re.findall(r"\.([\w-]+)", selectors))
    nodes = list(root.iter())
    return {
        "size (bytes)": len(raw),
        "gzip -9 (bytes)": len(gzip.compress(raw, 9)),
        "elements": len(nodes),
        "<text> elements": sum(1 for n in nodes if n.tag.endswith("text")),
        "animated elements": sum(1 for n in nodes if animated & set(n.get("class", "").split())),
        "@keyframes": len(re.findall(r"@keyframes", css)),
    }


def structure_checks(path):
    """Checks that need only the file: size of the picture, accessibility, safety."""
    raw, root = read_svg(path)
    tags = {el.tag.split("}")[-1].lower() for el in root.iter()}
    out = {}
    w, h = root.get("width"), root.get("height")
    if not (w and h) and root.get("viewBox"):
        w, h = root.get("viewBox").split()[2:4]
    out[f"size is {SPEC['width']}x{SPEC['height']}"] = (
        re.sub(r"px$", "", str(w)) == str(SPEC["width"]) and re.sub(r"px$", "", str(h)) == str(SPEC["height"])
    )
    out["role=img, <title> and <desc> present"] = root.get("role") == "img" and {"title", "desc"} <= tags
    out["no <script>, <foreignObject>, <image>"] = not ({"script", "foreignobject", "image"} & tags)
    attrs = [(k.split("}")[-1].lower(), v) for el in root.iter() for k, v in el.attrib.items()]
    out["no event handlers or external links"] = not any(
        k.startswith("on") or (k == "href" and not v.startswith("#")) for k, v in attrs
    )
    text = raw.decode("utf-8", "replace")
    out["no @import or url() to anything but #fragments"] = not (
        re.search(r"@import", text, re.I) or re.search(r"url\(\s*['\"]?\s*(?!#)", text, re.I)
    )
    return out


# ---------- browser (CPU and rendered frames) ----------

def cpu_metrics(path, seconds):
    from playwright.sync_api import sync_playwright

    svg = base64.b64encode(path.read_bytes()).decode()
    html = f'<body style="margin:0;background:#fff"><img src="data:image/svg+xml;base64,{svg}" width="656"></body>'
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--disable-background-timer-throttling"])
        page = browser.new_page(viewport={"width": 700, "height": 400})
        page.set_content(html)
        page.wait_for_timeout(1500)
        cdp = browser.new_browser_cdp_session()

        def snapshot():
            return {i["type"]: i["cpuTime"] for i in cdp.send("SystemInfo.getProcessInfo")["processInfo"]}

        before = snapshot()
        page.wait_for_timeout(int(seconds * 1000))
        after = snapshot()
        browser.close()
    delta = {k: 100 * (after[k] - before.get(k, 0)) / seconds for k in after}
    result = {"CPU, all processes (% of one core)": sum(delta.values())}
    for kind in ("renderer", "GPU"):
        if kind in delta:
            result[f"CPU, {kind} (% of one core)"] = delta[kind]
    return result


class Frames:
    """Renders the banner at chosen moments in time, in a given theme, the same way for every file."""

    def __init__(self, browser, path, scheme="light", reduced=False):
        from PIL import Image

        self.Image = Image
        raw = path.read_bytes()
        # the file may come from a pull request: no scripts, and no way out to the network
        ctx = browser.new_context(
            viewport={"width": SPEC["width"], "height": SPEC["height"]},
            color_scheme=scheme,
            reduced_motion="reduce" if reduced else "no-preference",
            java_script_enabled=False,  # page.evaluate() from Playwright still works
            service_workers="block",
        )
        ctx.route("**/*", lambda r: r.abort())  # registered first, so the route below wins for the banner only
        ctx.route("**/banner.svg", lambda r: r.fulfill(body=raw, content_type="image/svg+xml"))
        self.page = ctx.new_page()
        self.page.goto("http://banner.test/banner.svg")
        self.page.wait_for_timeout(200)
        self.running = self.page.evaluate(
            "document.getAnimations().length"
            " + document.querySelectorAll('animate,animateTransform,animateMotion,set').length"
        )

    def at(self, t):
        self.page.evaluate(
            """t => {
                const svg = document.documentElement;
                if (svg.pauseAnimations) { svg.pauseAnimations(); svg.setCurrentTime(t); }
                for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
            }""",
            t,
        )
        return self.Image.open(io.BytesIO(self.page.screenshot(type="png"))).convert("RGB")


def bright_mask(img, color):
    """Pixels close to the color of the 2s, as a black and white image."""
    from PIL import ImageChops

    mask = None
    for band, c in zip(img.split(), color):
        m = band.point(lambda v, c=c: 255 if abs(v - c) <= SPEC["color_distance"] // 2 else 0)
        mask = m if mask is None else ImageChops.darker(mask, m)
    return mask


def overlap(a, b):
    """IoU of two black and white masks."""
    from PIL import ImageChops

    inter = ImageChops.darker(a, b).histogram()[255]
    union = ImageChops.lighter(a, b).histogram()[255]
    return inter / union if union else 0.0


def flicker_stats(frames, step):
    """Share of cells that change and median toggles per second of those that do."""
    from PIL import ImageChops

    cols, rows = SPEC["grid"]
    cw, ch = SPEC["width"] / cols, SPEC["height"] / rows
    toggles = {}
    for a, b in zip(frames, frames[1:]):
        diff = ImageChops.difference(a.convert("L"), b.convert("L"))
        if not diff.getbbox():
            continue
        for r in range(rows):
            for c in range(cols):
                if diff.crop((int(c * cw), int(r * ch), int((c + 1) * cw), int((r + 1) * ch))).getbbox():
                    toggles[(r, c)] = toggles.get((r, c), 0) + 1
    window = step * (len(frames) - 1)
    rates = [n / window for n in toggles.values()]
    return len(toggles) / (cols * rows), (statistics.median(rates) if rates else 0.0)


def still(frames):
    from PIL import ImageChops

    return all(not ImageChops.difference(frames[0], f).getbbox() for f in frames[1:])


def sample(fr, start, stop, step):
    n = int(round((stop - start) / step))
    return [fr.at(start + i * step) for i in range(n + 1)]


def criteria_checks(ref_path, new_path):
    """Checks that look at the rendered picture. The reference file defines what the text looks like."""
    from playwright.sync_api import sync_playwright

    out = {}
    loop, scr, m = SPEC["loop"], SPEC["scramble"], SPEC["margin"]
    step = 0.025
    lo, hi = SPEC["rate"]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for scheme in ("light", "dark"):
            ref, new = Frames(browser, ref_path, scheme), Frames(browser, new_path, scheme)
            color = SPEC["ok_color"][scheme]
            # two loops: the flicker must restart each time, the text must stay still in between
            stats = [flicker_stats(sample(new, k * loop, k * loop + scr - m, step), step) for k in (0, 1)]
            holds = [sample(new, k * loop + scr + m, (k + 1) * loop - m, 0.2) for k in (0, 1)]
            text = overlap(bright_mask(new.at(loop - 0.5), color), bright_mask(ref.at(loop - 0.5), color))
            out[f"[{scheme}] flicker: >= {SPEC['min_share']:.0%} of cells change in the first {scr:g} s"] = all(
                s >= SPEC["min_share"] for s, _ in stats
            )
            out[f"[{scheme}] flicker speed: median {lo:g}-{hi:g} toggles/s per cell"] = all(lo <= r <= hi for _, r in stats)
            out[f"[{scheme}] text: still from {scr:g} s to the end of the {loop:g} s loop"] = all(still(h) for h in holds)
            out[f"[{scheme}] text: matches the reference (overlap >= {SPEC['match']:.0%})"] = text >= SPEC["match"]
        # reduced motion: nothing runs, the text is visible from the start
        ok = SPEC["ok_color"]["light"]
        calm, ref = Frames(browser, new_path, "light", reduced=True), Frames(browser, ref_path, "light")
        out["reduced motion: no animation runs"] = calm.running == 0
        out["reduced motion: the text is visible"] = (
            overlap(bright_mask(calm.at(0), ok), bright_mask(ref.at(loop - 0.5), ok)) >= SPEC["match"]
        )
        browser.close()
    return out


# ---------- report ----------

def table(columns, keys):
    width = max(len(k) for k in keys) + 2
    print("".ljust(width) + "".join(name.rjust(16) for name, _ in columns))
    for key in keys:
        cells = "".join(
            (f"{m[key]:.1f}" if isinstance(m[key], float) else f"{m[key]}").rjust(16) if key in m else "".rjust(16)
            for _, m in columns
        )
        print(key.ljust(width) + cells)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, default=[DEFAULT])
    ap.add_argument("--cpu", action="store_true", help="measure CPU time in Chrome")
    ap.add_argument("--check", action="store_true", help="check the acceptance criteria (implies --cpu)")
    ap.add_argument("--seconds", type=float, default=12, help="how long to measure CPU; the banner loops every 3 s")
    args = ap.parse_args()
    if args.check:
        args.cpu = True

    columns = []
    for f in args.files:
        m = static_metrics(f)
        if args.cpu:
            try:
                m.update(cpu_metrics(f, args.seconds))
            except ImportError:
                sys.exit("--cpu needs playwright: pip install playwright (and Google Chrome)")
        columns.append((f.name, m))
    table(columns, list(columns[0][1]))

    if not args.check:
        return
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("--check needs pillow: pip install pillow playwright (and Google Chrome)")
    ref_path, ref = args.files[0], columns[0][1]
    failed = False
    for path, (name, m) in zip(args.files, columns):
        print(f"\n{name}")
        results = structure_checks(path)
        if all(results.values()):  # never open a file in the browser before the safety checks pass
            results.update(criteria_checks(ref_path, path))
        else:
            results["browser checks skipped: fix the failed checks above first"] = False
        for label, ok in results.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        passed = all(results.values())
        if path != ref_path:
            cpu = "CPU, all processes (% of one core)"
            cpu_gain = (ref[cpu] - m[cpu]) / ref[cpu]
            size_gain = (ref["gzip -9 (bytes)"] - m["gzip -9 (bytes)"]) / ref["gzip -9 (bytes)"]
            better = cpu_gain >= SPEC["cpu_gain"] or (cpu_gain >= -SPEC["cpu_gain"] and size_gain >= SPEC["size_gain"])
            print(f"  {'PASS' if better else 'FAIL'}  better than the reference: CPU {cpu_gain:+.0%}, gzip size {size_gain:+.0%}")
            passed = passed and better
        print(f"  => {'ACCEPTABLE' if passed else 'NOT ACCEPTABLE'}")
        failed = failed or not passed
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
