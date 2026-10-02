"""Run the gate over the sample city-guide corpus.

SAMPLE DATA: the twelve pages in ./pages are fictional cities written for this
demo. Seven are one find-and-replace template with only the city name swapped.
Five are written page by page with their own detail. Every page is a full HTML
document with the same site header, nav, footer and analytics snippet.

Two modes, matching the gate's arming contract:

    # 1. Shadow (calibrate): score every page against the other eleven.
    python3 examples/city_guides/run_gate.py

    # 2. Enforce: publish the pages one by one in a mixed order. A page is
    #    compared with what is already live; a blocked page never goes live.
    python3 examples/city_guides/run_gate.py --enforce --threshold 0.40

Add --keep-chrome to score the pages WITHOUT stripping header/nav/footer.
Stdlib only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from homogeneity_gate import PROVISIONAL_THRESHOLD, HomogeneityGate  # noqa: E402

PAGES = HERE / "pages"
TEMPLATED = {"alderbrook", "bramwell", "calderon-falls", "dunmore-bay",
             "elkridge", "fenwick", "glenhollow"}
# Publish order for --enforce: templated and differentiated pages interleaved.
PUBLISH_ORDER = ["alderbrook", "harrowgate", "bramwell", "ivydale", "calderon-falls",
                 "juniper-flats", "dunmore-bay", "kestrel-point", "elkridge",
                 "larkspur", "fenwick", "glenhollow"]
CHROME = ("header", "nav", "footer")


def load_pages() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(PAGES.glob("*.html"))}


def kind(slug: str) -> str:
    return "templated" if slug in TEMPLATED else "differentiated"


def row(order: str, slug: str, verdict: str, score: float, compared: int, note: str) -> str:
    return f"{order:<5} {slug:<15} {kind(slug):<15} {verdict:<11} {score:>5.2f} {compared:>8}  {note}"


HEADER = f"{'#':<5} {'page':<15} {'kind':<15} {'verdict':<11} {'score':>5} {'compared':>8}  reason"


def shadow(pages: dict[str, str], gate: HomogeneityGate) -> None:
    print(f"SHADOW: each page vs the other {len(pages) - 1}, threshold {gate.threshold:.2f} "
          f"(calibrated: {gate.threshold_is_calibrated()})")
    print(HEADER)
    scores = {"templated": [], "differentiated": []}
    for i, (slug, text) in enumerate(pages.items(), 1):
        corpus = [(s, t) for s, t in pages.items() if s != slug]
        r = gate.evaluate(text, corpus)
        verdict = "WOULD-BLOCK" if r.would_block else "pass"
        scores[kind(slug)].append(r.score)
        print(row(str(i), slug, verdict, r.score, r.corpus_size_compared, r.reason or "-"))
    for k, v in scores.items():
        print(f"{k:<15} max-similarity range {min(v):.2f} to {max(v):.2f}")


def enforce(pages: dict[str, str], gate: HomogeneityGate) -> None:
    print(f"ENFORCE: publish in order, threshold {gate.threshold:.2f} "
          f"(calibrated: {gate.threshold_is_calibrated()})")
    print(HEADER)
    live: list[tuple[str, str]] = []
    blocked = 0
    for i, slug in enumerate(PUBLISH_ORDER, 1):
        r = gate.evaluate(pages[slug], live)
        if r.passed:
            live.append((slug, pages[slug]))
        else:
            blocked += 1
        print(row(str(i), slug, "PASS" if r.passed else "BLOCK", r.score,
                  r.corpus_size_compared, r.reason or "-"))
    print(f"published {len(live)}, blocked {blocked}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--enforce", action="store_true", help="hold pages over the threshold")
    ap.add_argument("--threshold", type=float, default=PROVISIONAL_THRESHOLD)
    ap.add_argument("--keep-chrome", action="store_true",
                    help="do not strip header/nav/footer before scoring")
    args = ap.parse_args(argv)

    gate = HomogeneityGate(
        threshold=args.threshold,
        enforce=args.enforce,
        boilerplate_tags=() if args.keep_chrome else CHROME,
    )
    pages = load_pages()
    if len(pages) != 12:
        print(f"expected 12 sample pages in {PAGES}, found {len(pages)}", file=sys.stderr)
        return 1
    (enforce if args.enforce else shadow)(pages, gate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
