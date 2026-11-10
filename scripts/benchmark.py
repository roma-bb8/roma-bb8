#!/usr/bin/env python3
"""Measure a banner and check it against the acceptance criteria (the table is in CONTRIBUTING.md).

    python3 scripts/benchmark.py                           measure image/banner.svg alone
    python3 scripts/benchmark.py old.svg new.svg           size and structure              (no dependencies)
    python3 scripts/benchmark.py --cpu old.svg new.svg     + CPU time in Chrome            (pip install playwright, Chrome)
    python3 scripts/benchmark.py --check old.svg new.svg   + the acceptance criteria       (pip install playwright pillow, Chrome)

The first file is the reference, normally the current image/banner.svg. Every other file is compared with it.
The exit code is 1 if any file fails a check, so the command works as a CI step.

Optional reports for CI (the last file is the one that is reported):

    --markdown FILE      a Markdown summary: GitHub shows it on the run page ($GITHUB_STEP_SUMMARY)
    --openmetrics FILE   metric lines: GitLab shows them in the merge request (artifacts:reports:metrics)

The criteria are defined twice: as a table for people in CONTRIBUTING.md, and as SPEC below for the machine.
Change both together.

Safety: banners come from pull requests, so they are untrusted. A banner is only parsed as XML and opened in
a browser with JavaScript and the network switched off. It is never executed here.
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

# Acceptance criteria, as numbers. Keep in sync with the table in CONTRIBUTING.md.
SPEC = {
    "width": 656,
    "height": 121,
    "grid": (80, 10),  # columns, rows of digits; the picture is cut into these cells to see which ones change
    "loop": 3.0,  # seconds for the whole animation
    "scramble": 1.0,  # seconds: the first second of a loop flickers, the rest is a still "Hello, world!"
    "margin": 0.1,  # seconds to skip on each side of the border between flicker and still text
    "min_share": 0.30,  # at least this share of the cells must flicker while scrambling
    "rate": (2.0, 8.0),  # median toggles per second of a flickering cell
    "match": 0.90,  # overlap (intersection over union) of the bright "2" pixels with the reference text
    "ok_color": {"light": (0x21, 0x6E, 0x39), "dark": (0x79, 0xCF, 0x71)},  # color of the 2s per theme
    "color_distance": 60,  # how far a pixel channel may be from the color of the 2s and still count as one (per channel, +-30)
    "cpu_gain": 0.05,  # a new banner must use at least 5% less CPU ...
    "size_gain": 0.10,  # ... or be at least 10% smaller (gzip) while its CPU is within 5% of the reference
}


# ---------- Static metrics and safety checks (standard library only) ----------

def read_svg(path):
    """The bytes and the parsed XML of a banner; refuses files that could abuse the parser."""
    raw = path.read_bytes()
    # untrusted input: the stdlib XML parser is open to entity-expansion attacks and a banner needs no DOCTYPE
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        sys.exit(f"{path}: DOCTYPE and ENTITY declarations are not allowed in the banner")
    return raw, ET.fromstring(raw)


def static_metrics(path):
    """Numbers that describe the file itself: size, element counts, how much of it is animated."""
    raw, root = read_svg(path)
    css = " ".join(el.text or "" for el in root.iter() if el.tag.endswith("style"))
    animated = set()  # CSS classes that have an animation
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
    """Checks that need only the file: picture size, accessibility, safety. Returns {label: passed}."""
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


# ---------- Browser: CPU time and rendered frames ----------

def cpu_metrics(path, seconds):
    """CPU used by Chrome while it shows the banner for `seconds`, in % of one core."""
    from playwright.sync_api import sync_playwright

    svg = base64.b64encode(path.read_bytes()).decode()
    html = f'<body style="margin:0;background:#fff"><img src="data:image/svg+xml;base64,{svg}" width="656"></body>'
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", args=["--disable-background-timer-throttling"])
        page = browser.new_page(viewport={"width": 700, "height": 400})
        page.set_content(html)
        page.wait_for_timeout(1500)  # let the page settle before measuring
        cdp = browser.new_browser_cdp_session()

        def snapshot():
            # total CPU seconds used so far by each Chrome process (renderer, GPU, browser, ...)
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
    """Shows a banner in Chrome and takes screenshots at chosen moments of its timeline.

    Every file is rendered the same way: same size, same theme, JavaScript off, no network.
    """

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
        # how many animations are running right now (CSS and SMIL); used by the reduced-motion check
        self.running = self.page.evaluate(
            "document.getAnimations().length"
            " + document.querySelectorAll('animate,animateTransform,animateMotion,set').length"
        )

    def at(self, t):
        """Screenshot of the banner at second `t` of its timeline (the animations are paused there)."""
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
    """True if all the frames are pixel-identical."""
    from PIL import ImageChops

    return all(not ImageChops.difference(frames[0], f).getbbox() for f in frames[1:])


def sample(fr, start, stop, step):
    """Screenshots from `start` to `stop` seconds, one every `step` seconds."""
    n = int(round((stop - start) / step))
    return [fr.at(start + i * step) for i in range(n + 1)]


def criteria_checks(ref_path, new_path):
    """Checks that look at the rendered picture. The reference file defines what the text looks like.

    Both themes are tested over two loops: the flicker must restart each time, and the text must stay still between.
    """
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
            # flicker windows and still windows of loops 0 and 1; the margin keeps clear of the border between phases
            stats = [flicker_stats(sample(new, k * loop, k * loop + scr - m, step), step) for k in (0, 1)]
            holds = [sample(new, k * loop + scr + m, (k + 1) * loop - m, 0.2) for k in (0, 1)]
            text = overlap(bright_mask(new.at(loop - 0.5), color), bright_mask(ref.at(loop - 0.5), color))
            out[f"[{scheme}] flicker: >= {SPEC['min_share']:.0%} of cells change in the first {scr:g} s"] = all(
                s >= SPEC["min_share"] for s, _ in stats
            )
            out[f"[{scheme}] flicker speed: median {lo:g}-{hi:g} toggles/s per cell"] = all(lo <= r <= hi for _, r in stats)
            out[f"[{scheme}] text: still from {scr:g} s to the end of the {loop:g} s loop"] = all(still(h) for h in holds)
            out[f"[{scheme}] text: matches the reference (overlap >= {SPEC['match']:.0%})"] = text >= SPEC["match"]
        # reduced motion: no animation runs, and the text is there from the first frame
        ok = SPEC["ok_color"]["light"]
        calm, ref = Frames(browser, new_path, "light", reduced=True), Frames(browser, ref_path, "light")
        out["reduced motion: no animation runs"] = calm.running == 0
        out["reduced motion: the text is visible"] = (
            overlap(bright_mask(calm.at(0), ok), bright_mask(ref.at(loop - 0.5), ok)) >= SPEC["match"]
        )
        browser.close()
    return out


# ---------- Report ----------

def table(columns, keys):
    """Prints the metrics of all files side by side, one column per file."""
    width = max(len(k) for k in keys) + 2
    print("".ljust(width) + "".join(name.rjust(16) for name, _ in columns))
    for key in keys:
        cells = "".join(
            (f"{m[key]:.1f}" if isinstance(m[key], float) else f"{m[key]}").rjust(16) if key in m else "".rjust(16)
            for _, m in columns
        )
        print(key.ljust(width) + cells)


def write_markdown(path, columns, verdicts):
    """A Markdown summary for people: the metrics table, then PASS/FAIL per file when the criteria were checked."""
    keys = list(columns[0][1])
    lines = ["## Banner benchmark", "", "| | " + " | ".join(name for name, _ in columns) + " |"]
    lines.append("|:--|" + "--:|" * len(columns))
    for key in keys:
        cells = (f"{m[key]:.1f}" if isinstance(m.get(key), float) else str(m.get(key, "")) for _, m in columns)
        lines.append(f"| {key.replace('<', '&lt;')} | " + " | ".join(cells) + " |")
    for name, (results, passed) in verdicts.items():
        lines += ["", f"### {name}: {'✅ acceptable' if passed else '❌ not acceptable'}", ""]
        lines += [f"- {'✅' if ok else '❌'} {label}" for label, ok in results.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_openmetrics(path, columns):
    """Metrics of the last file, one `name value` per line, for the GitLab merge request widget."""
    names = {
        "size (bytes)": "banner_size_bytes",
        "gzip -9 (bytes)": "banner_gzip_bytes",
        "elements": "banner_elements",
        "animated elements": "banner_animated_elements",
        "@keyframes": "banner_keyframes",
        "CPU, all processes (% of one core)": "banner_cpu_percent",
    }
    _, last = columns[-1]
    lines = [f"{names[k]} {last[k]:.2f}" for k in names if k in last]
    path.write_text("\n".join(lines) + "\n# EOF\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, default=[DEFAULT], help="the reference first, then the banners to compare")
    ap.add_argument("--cpu", action="store_true", help="measure CPU time in Chrome")
    ap.add_argument("--check", action="store_true", help="check the acceptance criteria (implies --cpu)")
    ap.add_argument("--seconds", type=float, default=12, help="how long to measure CPU; the banner loops every 3 s")
    ap.add_argument("--markdown", type=Path, metavar="FILE", help="also write a Markdown summary")
    ap.add_argument("--openmetrics", type=Path, metavar="FILE", help="also write metrics for GitLab merge requests")
    args = ap.parse_args()
    if args.check:
        args.cpu = True

    # 1. Measure every file. Each column is (file name, {metric: value}).
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

    # 2. Check the criteria of every file against the first one. verdicts: {name: ({check: passed}, all passed)}.
    verdicts, failed = {}, False
    if args.check:
        try:
            import PIL  # noqa: F401
        except ImportError:
            sys.exit("--check needs pillow: pip install pillow playwright (and Google Chrome)")
        ref_path, ref = args.files[0], columns[0][1]
        for path, (name, m) in zip(args.files, columns):
            print(f"\n{name}")
            results = structure_checks(path)
            if all(results.values()):  # never open a file in the browser before the safety checks pass
                results.update(criteria_checks(ref_path, path))
            else:
                results["browser checks skipped: fix the failed checks above first"] = False
            if path != ref_path:  # the reference cannot be cheaper than itself
                cpu = "CPU, all processes (% of one core)"
                cpu_gain = (ref[cpu] - m[cpu]) / ref[cpu]
                size_gain = (ref["gzip -9 (bytes)"] - m["gzip -9 (bytes)"]) / ref["gzip -9 (bytes)"]
                better = cpu_gain >= SPEC["cpu_gain"] or (cpu_gain >= -SPEC["cpu_gain"] and size_gain >= SPEC["size_gain"])
                results[f"cheaper than the reference: CPU {cpu_gain:+.0%}, gzip size {size_gain:+.0%}"] = better
            for label, ok in results.items():
                print(f"  {'PASS' if ok else 'FAIL'}  {label}")
            passed = all(results.values())
            print(f"  => {'ACCEPTABLE' if passed else 'NOT ACCEPTABLE'}")
            verdicts[name] = (results, passed)
            failed = failed or not passed

    # 3. Reports for CI, written even when a check failed so that the reason is visible.
    if args.markdown:
        write_markdown(args.markdown, columns, verdicts)
    if args.openmetrics:
        write_openmetrics(args.openmetrics, columns)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
