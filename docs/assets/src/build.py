"""Build the README graphics.

Data graphics (hero, anatomy, calibration) read ONLY from the committed captures in
./captures, written by the kit's capture.py from real runs of
examples/city_guides/run_gate.py. The architecture graphic is structural and reads
its constants from the source modules. Nothing here types a score by hand.

    python3 docs/assets/src/build.py
    uv run --with playwright==1.56.0 --with pillow python docs/assets/src/render.py docs/assets/src docs/assets
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import readme_kit as rk  # noqa: E402
import homogeneity_gate as hg  # noqa: E402
import text_similarity as ts  # noqa: E402

CAP = HERE / "captures"
REPO = "CONTENT_HOMOGENEITY_GATE"
esc = rk.esc

ROW = re.compile(r"^(\d+)\s+(\S+)\s+(templated|differentiated)\s+(\S+)\s+([\d.]+)\s+(\d+)\s+(.*)$")


def cap(name: str) -> dict:
    return rk.load_capture(CAP / f"{name}.json")


def run_date(c: dict) -> str:
    """Capture date in US Central time (the author's local date)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.fromisoformat(c["captured_at"]).astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")


def rows(c: dict) -> list[dict]:
    out = []
    for line in c["output"].splitlines():
        m = ROW.match(line)
        if m:
            out.append(dict(n=int(m[1]), page=m[2], kind=m[3], verdict=m[4], score=float(m[5]),
                            compared=int(m[6]), reason=m[7]))
    if not out:
        raise SystemExit(f"no rows parsed from capture {c['name']}")
    return out


def header_threshold(c: dict) -> float:
    return float(re.search(r"threshold ([\d.]+)", c["output"]).group(1))


def pair_fields(c: dict) -> dict:
    o = c["output"]
    m = re.search(r"^PAIR: (\S+) \((\w+)\) vs (\S+) \((\w+)\)", o, re.M)
    a, b = m[1], m[3]
    sh = re.search(r"shingles: \S+ (\d+), \S+ (\d+), shared (\d+), union (\d+)", o)
    return dict(
        a=a, b=b, kind=m[2],
        a_open=re.search(rf"^{re.escape(a)} opens: (.*)$", o, re.M)[1],
        b_open=re.search(rf"^{re.escape(b)} opens: (.*)$", o, re.M)[1],
        diff=re.search(r"^words in \S+ not in \S+: (.*)$", o, re.M)[1],
        na=int(sh[1]), nb=int(sh[2]), shared=int(sh[3]), union=int(sh[4]),
        jac=re.search(r"^jaccard: .* = ([\d.]+)$", o, re.M)[1],
        verdict=re.search(r"^verdict at threshold ([\d.]+): (\S+)\s+(.*)$", o, re.M),
    )


# ── hero ─────────────────────────────────────────────────────────────────────────────────

def build_hero() -> str:
    c = cap("enforce")
    rs = rows(c)
    blocked = sum(r["verdict"] == "BLOCK" for r in rs)
    items = "".join(
        f"<div style='display:flex;align-items:center;gap:14px;height:38px;border-bottom:1px solid var(--line)'>"
        f"<div class='mono' style='width:24px;color:var(--dim);font-size:13px'>{r['n']:02d}</div>"
        f"<div class='mono' style='width:140px;font-size:14px'>{esc(r['page'])}</div>"
        f"<div style='width:110px;font-size:13px;color:var(--muted)'>{esc(r['kind'])}</div>"
        f"<div class='mono' style='width:56px;font-size:15px;text-align:right'>{r['score']:.2f}</div>"
        f"<div class='mono' style='margin-left:auto;font-size:13px;letter-spacing:.12em;padding:4px 10px;border-radius:6px;"
        f"border:1.5px solid {'var(--bad)' if r['verdict'] == 'BLOCK' else 'var(--good)'};"
        f"color:{'var(--bad)' if r['verdict'] == 'BLOCK' else 'var(--good)'}'>{'&#9632; BLOCK' if r['verdict'] == 'BLOCK' else '&#9679; PASS'}</div></div>"
        for r in rs)
    right = (f"<div class='card' style='width:600px;padding:16px 22px'>"
             f"<div class='k' style='font-size:12px;margin-bottom:6px'>12 sample pages, published in order, threshold {header_threshold(c):.2f}</div>"
             f"{items}<div class='mono' style='margin-top:10px;font-size:13px;color:var(--muted)'>{esc(c['output'].strip().splitlines()[-1])}</div></div>")
    return rk.hero(
        "CONTENT_HOMOGENEITY_GATE",
        "Stop the template", "before it ships.",
        "A pure-stdlib gate that scores each draft against the pages you already published "
        f"and holds the near-duplicates. Real run on a fictional city-guide corpus: {blocked} find-and-replace copies held, "
        "every hand-written page through.",
        [("Shingle Jaccard, exact", f"{ts.DEFAULT_SHINGLE_K}-word shingles, deterministic, no ML, no network."),
         ("Ships in shadow mode", "Measures and logs would_block until you calibrate a threshold."),
         ("Fails closed when armed", "A crashed gate holds the draft instead of publishing it.")],
        "STDLIB ONLY · PYTHON 3.9+",
        right,
        f"{REPO} · REAL RUN {run_date(c)}",
    )


# ── anatomy: templated pair vs differentiated pair ──────────────────────────────────────

def pair_card(p: dict, x: int, bad: bool) -> str:
    col = "var(--bad)" if bad else "var(--good)"
    v = p["verdict"]
    reason = v[3] if v[3] != "-" else f"similarity {float(p['jac']):.3f} < threshold {float(v[1]):.3f}"
    pct = p["shared"] / p["union"] if p["union"] else 0
    return (
        f"<div class='card' style='position:absolute;left:{x}px;top:186px;width:628px;height:500px;padding:24px 28px;border-color:{col}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div class='k' style='color:{col}'>{'TEMPLATED PAIR' if bad else 'DIFFERENTIATED PAIR'}</div>"
        f"<div class='mono' style='font-size:15px;letter-spacing:.12em;color:{col};border:1.5px solid {col};border-radius:6px;padding:5px 12px'>"
        f"{'&#9632; ' if bad else '&#9679; '}{esc(v[2])}</div></div>"
        f"<div class='mono' style='font-size:13px;color:var(--dim);margin-top:18px'>{esc(p['a'])} opens</div>"
        f"<div class='mono' style='font-size:14px;line-height:1.45;margin-top:4px'>{esc(p['a_open'])}</div>"
        f"<div class='mono' style='font-size:13px;color:var(--dim);margin-top:12px'>{esc(p['b'])} opens</div>"
        f"<div class='mono' style='font-size:14px;line-height:1.45;margin-top:4px'>{esc(p['b_open'])}</div>"
        f"<div style='font-size:15px;color:var(--muted);margin-top:16px'>Words in {esc(p['a'])} that {esc(p['b'])} lacks:</div>"
        f"<div class='mono' style='font-size:15px;margin-top:4px;color:var(--amber)'>{esc(p['diff'])}</div>"
        f"<div style='margin-top:22px;height:14px;border-radius:7px;background:#221f1c;overflow:hidden'>"
        f"<div style='height:14px;width:{max(pct * 100, 0.6):.1f}%;background:{col};border-radius:7px'></div></div>"
        f"<div class='mono' style='font-size:14px;color:var(--muted);margin-top:8px'>shared {p['shared']} of {p['union']} five-word shingles</div>"
        f"<div style='display:flex;align-items:baseline;gap:14px;margin-top:16px'>"
        f"<div class='serif' style='font-size:54px;color:{col}'>{esc(p['jac'])}</div>"
        f"<div style='font-size:15px;color:var(--muted)'>Jaccard similarity</div></div>"
        f"<div class='mono' style='font-size:13px;color:var(--ivory);margin-top:6px'>{esc(reason)}</div></div>")


def build_anatomy() -> str:
    t, d = cap("pair_templated"), cap("pair_differentiated")
    pt, pd = pair_fields(t), pair_fields(d)
    body = (rk.heading("ANATOMY OF A VERDICT",
                       f"Same template, new city name: {rk.em('held')}. Real detail: {rk.em('passed')}.")
            + "<div style='position:absolute;left:56px;top:142px;color:var(--muted);font-size:16px'>"
              "Output of <span class='mono'>run_gate.py --pair</span> on the fictional sample corpus, site header, nav and footer stripped.</div>"
            + pair_card(pt, 56, True) + pair_card(pd, 716, False))
    return rk.page(body, "anatomy", f"{REPO} · REAL RUN {run_date(t)}")


# ── calibration strip ───────────────────────────────────────────────────────────────────

def build_calibration() -> str:
    sh, kc, en = cap("shadow"), cap("shadow_keep_chrome"), cap("enforce")
    thr, prov = header_threshold(en), header_threshold(sh)
    x0, x1 = 300, 1320

    def X(v: float) -> float:
        return x0 + v * (x1 - x0)

    def strip(rs: list[dict], y: int, label: str, sub: str) -> str:
        out = (f"<div style='position:absolute;left:56px;top:{y - 22}px;width:160px'><div style='font-size:17px;font-weight:600'>{esc(label)}</div>"
               f"<div style='font-size:13px;color:var(--muted);margin-top:4px'>{esc(sub)}</div></div>"
               f"<div style='position:absolute;left:{x0}px;width:{x1 - x0}px;top:{y}px;height:1px;background:var(--line)'></div>")
        groups: dict[tuple[str, float], int] = {}
        for r in rs:
            key = (r["kind"], r["score"])
            i = groups.get(key, 0)
            groups[key] = i + 1
            bad = r["kind"] == "templated"
            dy = (-16 - i * 13) if bad else (16 + i * 13)
            shape = "border-radius:2px" if bad else "border-radius:50%"
            out += (f"<div title='{esc(r['page'])} {r['score']:.2f}' style='position:absolute;left:{X(r['score']) - 6:.0f}px;top:{y + dy - 6}px;width:12px;height:12px;"
                    f"{shape};background:{'var(--bad)' if bad else 'var(--good)'};box-shadow:0 0 0 2px var(--bg)'></div>")
        for kind, bad in (("templated", True), ("differentiated", False)):
            v = [r["score"] for r in rs if r["kind"] == kind]
            lo, hi = min(v), max(v)
            txt = f"{kind} {lo:.2f}" if lo == hi else f"{kind} {lo:.2f} to {hi:.2f}"
            n = max(sum(1 for r in rs if r["kind"] == kind and r["score"] == s) for s in v)
            yy = (y - 16 - n * 13 - 22) if bad else (y + 16 + n * 13 + 4)
            out += (f"<div class='mono' style='position:absolute;left:{X(lo) - 4:.0f}px;top:{yy}px;font-size:13px;color:var(--ivory)'>"
                    f"{'&#9632;' if bad else '&#9679;'} {esc(txt)}</div>")
        return out

    ticks = "".join(
        f"<div class='mono' style='position:absolute;left:{X(v) - 14:.0f}px;top:640px;font-size:12px;color:var(--dim)'>{v:.1f}</div>"
        for v in (0, .2, .4, .6, .8, 1.0))
    vline = lambda v, col, lab, top: (  # noqa: E731
        f"<div style='position:absolute;left:{X(v):.0f}px;top:200px;width:2px;height:430px;background:{col};opacity:.85'></div>"
        f"<div class='mono' style='position:absolute;left:{X(v) + 8:.0f}px;top:{top}px;font-size:13px;color:{col}'>{esc(lab)}</div>")
    body = (rk.heading("CALIBRATE IN SHADOW, THEN ARM",
                       f"The gap between the two groups {rk.em('is')} the threshold.",
                       "Shadow mode scored each of the 12 sample pages against the other 11 and blocked nothing. "
                       "Keeping identical site chrome in the text lifts every unique page off zero.")
            + vline(thr, "var(--amber)", f"armed at {thr:.2f}", 196)
            + vline(prov, "var(--dim)", f"provisional default {prov:.2f} (uncalibrated)", 196)
            + strip(rows(sh), 340, "chrome stripped", "boilerplate_tags = header, nav, footer")
            + strip(rows(kc), 520, "chrome kept", "same pages, no boilerplate_tags")
            + ticks
            + "<div class='mono' style='position:absolute;left:300px;top:664px;font-size:12px;color:var(--dim)'>max similarity to any other page</div>")
    return rk.page(body, "calibration", f"{REPO} · REAL RUN {run_date(sh)}")


# ── architecture (structural) ───────────────────────────────────────────────────────────

def build_architecture() -> str:
    b = rk.box
    boxes = (
        b(56, 230, 220, 150, "Draft + corpus", ["evaluate(draft, [(ref, text), ...])", "you supply the corpus;", "the gate queries nothing"])
        + b(316, 230, 220, 150, "Normalize", ["drop script, style, comments", "decode entities", "optional boilerplate_tags"])
        + b(576, 230, 260, 150, "Pre-filter", [f">= {ts.DEFAULT_PREFILTER_MIN_OVERLAP} shared distinctive keywords", f"OR keyword Jaccard >= {ts.DEFAULT_PREFILTER_RESCUE_RATIO}", "(template rescue)"])
        + b(876, 230, 210, 150, "Score", [f"{ts.DEFAULT_SHINGLE_K}-word shingle Jaccard", "best match across corpus", "score + match ref"], accent=True)
        + b(1126, 130, 218, 150, "Shadow", ["enforce=False, default", "always passes", "sets would_block"])
        + b(1126, 330, 218, 150, "Enforce", ["score >= threshold", "BLOCK + match ref", "crash: fail closed"])
        + b(576, 520, 768, 120, "Calibration signal", [f"threshold_is_calibrated() is False while threshold == {hg.PROVISIONAL_THRESHOLD}",
                                                       "wire it into your arming check before enforce=True"])
        + b(56, 520, 480, 120, "gate_signal(records)", ["block rate, fail-closed count", "review_queue_depth is all-time, never windowed"])
    )
    arr = ([(276, 305, 316, 305), (536, 305, 576, 305), (836, 305, 876, 305),
                     (1086, 280, 1126, 215), (1086, 330, 1126, 395), (981, 520, 981, 380, "sets threshold", True, "right")])
    return rk.flow("HOW IT WORKS", f"One draft in, one {rk.em('verdict')} out.",
                   "homogeneity_gate.py + text_similarity.py · stdlib only · no I/O", boxes, arr,
                   f"{REPO} · HOW IT WORKS")


if __name__ == "__main__":
    rk.write_pages(HERE, {
        "hero": build_hero(),
        "anatomy": build_anatomy(),
        "calibration": build_calibration(),
        "architecture": build_architecture(),
    })
