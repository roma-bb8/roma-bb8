# Contributing

This is a profile repository: its [`README.md`](./README.md) is shown on [github.com/roma-bb8](https://github.com/roma-bb8). There is nothing to build or test, except the banner (see [Make the banner cheaper](#make-the-banner-cheaper)).

Useful contributions:

- Fixing a typo, a broken link, or a wrong fact in the README.
- Suggesting a better wording (English is not my first language).
- Making the banner at the top of the README cheaper. People and agents are both welcome, and an accepted author is credited.

## How to contribute

1. Open an [issue](../../issues/new/choose) first if the change is more than a typo.
2. Fork the repository and make a small, focused change.
3. Open a pull request and fill in the template.

Follow the [Code of Conduct](./CODE_OF_CONDUCT.md) and the [Accessibility guidelines](./ACCESSIBILITY.md).

## Make the banner cheaper

The banner at the top of the README is an animated SVG ([`image/banner.svg`](./image/banner.svg)) made by [`scripts/gen_banner.py`](./scripts/gen_banner.py). It looks simple, but it still uses CPU on the page. **Can you make it cheaper?**

I will merge a pull request that passes every criterion below, together with the output of the check, and credit its author in the line under the banner.

### Criteria

| What               | Criterion                                                                                                           |
| :----------------- | :------------------------------------------------------------------------------------------------------------------ |
| 🖼️ Picture         | SVG, 656×121, `role="img"` with `<title>` and `<desc>`. No scripts, `<foreignObject>`, `<image>` or external links. |
| 🔁 Loop            | 3 seconds, then it repeats.                                                                                         |
| ✨ Flicker (0–1 s) | At least 30% of the digits flip between `0` and `1`; each flickering digit toggles 2–8 times per second (median).   |
| 🔤 Text (1–3 s)    | Nothing moves. The `2` digits spell "Hello, world!" and match the current text (90% overlap).                       |
| 🌗 Themes          | Both light and dark. The `2` digits stay `#216e39` (light) and `#79cf71` (dark).                                    |
| 🧘 Reduced motion  | With `prefers-reduced-motion: reduce` nothing runs and the text is visible from the start.                          |
| 📉 Cheaper         | At least 5% less CPU than the current banner, or at least 10% smaller (gzip) with CPU within 5%.                    |

The numbers live in `SPEC` in [`scripts/benchmark.py`](./scripts/benchmark.py). If this table and `SPEC` disagree, `SPEC` is what runs.

### Check it

Save a copy of the current banner as the reference, change the banner, and compare:

```sh
pip install playwright pillow          # and Google Chrome
cp image/banner.svg /tmp/reference.svg
python3 scripts/gen_banner.py          # or your own generator
python3 scripts/benchmark.py --check /tmp/reference.svg image/banner.svg
```

The last line for your file must be `=> ACCEPTABLE`. Without `--check` the script only prints size and structure; with `--cpu` it also measures CPU time. Read the top of [`scripts/gen_banner.py`](./scripts/gen_banner.py) for how the banner is built and where the CPU goes.

### Send it

1. Fork the repository and change [`scripts/gen_banner.py`](./scripts/gen_banner.py), then run it, so that the banner can be reproduced.
2. Open a pull request with the [banner template](../../compare?quick_pull=1&template=banner.md) and paste the output of the check.
3. A workflow runs the same check on your pull request and shows the result on the run page (the **Summary** of the **Banner** run). It is a first look: CPU time on a shared runner is noisy, so I repeat the check on my machine before merging.
4. If your banner is merged, you are credited under it. Write in the template how you want to be named.

### For agents

- Change [`scripts/gen_banner.py`](./scripts/gen_banner.py) and regenerate `image/banner.svg`. Do not edit the SVG by hand.
- Do not change `SPEC` or the checks in `scripts/benchmark.py` in the same pull request. The workflow runs the script from the base branch, so such a change does not help, and it will be rejected.
- Paste real output of `--check`, not a summary of it. If a criterion fails, say so.
- Say in the template that an agent made the change, and which one.

Happy Coding! 😉
