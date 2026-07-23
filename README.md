# content_homogeneity_gate

**The anti-templating quality floor for AI-generated content at scale.**

When you generate content programmatically — 500 city pages, 10,000 game recaps — the failure that gets a site de-indexed isn't thin content, it's **near-duplicate** content: pages that read like each other because the same model filled the same template. Search engines collapse them.

This gate scores a draft against **the corpus your own engine already published** and blocks the ones that are too similar, *before* they go live. It's ~200 lines of pure stdlib — deterministic shingle-Jaccard behind a distinctive-keyword pre-filter. No ML, no network, no database.

```python
from homogeneity_gate import HomogeneityGate

gate = HomogeneityGate(
    threshold=0.62,          # calibrated from YOUR score distribution
    enforce=True,
    prefilter_stopwords=MY_DOMAIN_VOCABULARY,
)

# You supply the corpus — [(ref, text), ...]. The gate never queries anything.
corpus = [(p.slug, p.body) for p in already_published_pages]
result = gate.evaluate(draft_html, corpus)

if not result.passed:
    hold_for_review(draft, reason=result.reason, near_duplicate=result.match_ref)
```

## Why intra-corpus, and why that's the gap

It checks for near-duplicates of **your own other pages**, not of the open web — that's Copyscape's and Originality.ai's job. Scaled *self-cannibalization* is the specific failure mode of programmatic SEO, and nobody packages a gate for it. `datasketch` gives you the MinHash primitive; nobody gives you the gate — the shadow mode, the calibration refusal, the fail-closed contract, the observability.

## It ships inert — on purpose

A similarity threshold you haven't calibrated against your own content is a number you made up, and enforcing a made-up threshold will silently cap your throughput or drop good pages. So the gate ships in **shadow mode**:

- **`enforce=False`** (default): computes and returns the score and a `would_block` flag, but **always passes**. Run it live, collect the score distribution, pick a real threshold from data.
- **`threshold_is_calibrated()`** is `False` while the threshold sits at its provisional default (`0.55`). Wire it into your arming precondition so nobody flips `enforce=True` before the threshold means anything:

  ```python
  if not gate.threshold_is_calibrated():
      raise RuntimeError("refusing to enforce an uncalibrated homogeneity threshold")
  ```

- Only with **`enforce=True`** does a block hold a draft — and only then is the **fail-closed** contract active: a *crashed* gate holds the draft for review rather than letting it auto-publish. In shadow mode a crash records the error and passes, because a measurement tool must never drop content.

On a brand-new engine the corpus is empty, so the gate is a safe no-op until content accumulates.

## The distinctive-keyword pre-filter

Naively, scoring a candidate against a corpus is O(candidate × whole-corpus) on every publish. The pre-filter cuts that: a corpus document is only shingle-scored if it shares enough **distinctive** keywords with the candidate.

The subtlety is *distinctive*. Same-domain prose shares a heavy generic vocabulary — a sports-recap corpus shares "quarterback", "touchdown", "defeated" — so a naive "shares ≥1 keyword" filter degenerates to "compare against everything." You pass a `prefilter_stopwords` set (your domain's ubiquitous vocabulary) so the filter keys on the tokens that actually distinguish one page from another: proper nouns, places, numbers.

`examples/sports_stopwords.py` is a worked set for a multi-sport recap corpus. Build the equivalent for your domain.

## Django integration

The gate has **no Django dependency** — you supply the corpus, so the ORM stays on your side of the line. A typical wiring reads config from `settings` and the corpus from a queryset:

```python
from django.conf import settings
from homogeneity_gate import HomogeneityGate

def build_gate():
    return HomogeneityGate(
        threshold=settings.HOMOGENEITY_THRESHOLD,
        enforce=settings.HOMOGENEITY_ENFORCE,
        prefilter_stopwords=MY_STOPWORDS,
    )

def check_before_publish(page):
    # Scope the corpus to what actually competes for indexing — same site,
    # same content type, optionally a recency window and a row cap.
    corpus = [
        (p.slug, p.body)
        for p in Page.objects.filter(site=page.site, kind=page.kind)
                             .exclude(pk=page.pk)
                             .order_by("-created_at")[:200]
    ]
    return build_gate().evaluate(page.body, corpus)
```

Call it from a `pre_save` signal, a publish pipeline, or a Celery task — the gate is identical in all three.

## Observability

`gate_signal(records)` rolls a batch of persisted outcomes into a summary — block rate, fail-closed count, and review-queue depth. One deliberate asymmetry: **`review_queue_depth` is all-time, not windowed.** A held draft stays a problem until a human clears it, so a windowed queue-depth would quietly report zero the day after a block — the exact blind spot the number exists to prevent. You map your stored rows onto `SignalRecord` and pass them in; the function has no clock and no database.

## Scale

This is an exact O(n) shingle compare behind a keyword block. At corpus sizes where that stops being cheap, the documented next step is MinHash + LSH (e.g. [`datasketch`](https://github.com/ekzhu/datasketch)) for approximate near-duplicate blocking. This package deliberately doesn't pull that dependency in — stdlib only, deterministic, easy to reason about.

## Tests

```bash
cd tests && python3 -m unittest discover -v
```

28 tests, stdlib `unittest`, no dependencies. The largest group asserts the pre-filter's pruning behavior on realistic shared-vocabulary prose — the part that's easy to get subtly wrong.

## License

MIT

---

## Part of a larger system

`content_homogeneity_gate` is one of the reusable pieces pulled out of a private, autonomous build
system and released on its own — the machine needed it, so it built it, and now
it's yours too, MIT-licensed.

See the rest of the parts → **https://autonomousaj.com/parts**
