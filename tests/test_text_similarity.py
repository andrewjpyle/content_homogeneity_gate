"""Tests for the text_similarity primitive.

Stdlib unittest — the primitive has no dependencies and neither does its suite.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import text_similarity as ts  # noqa: E402
from sports_stopwords import SPORTS_STOPWORDS  # noqa: E402


class ShingleJaccard(unittest.TestCase):
    def test_identical_text_is_one(self):
        t = "the quick brown fox jumped over the lazy dog again and again"
        self.assertEqual(ts.shingle_jaccard(t, t), 1.0)

    def test_disjoint_text_is_zero(self):
        a = "alpha bravo charlie delta echo foxtrot golf hotel india"
        b = "the cat sat on a warm mat beside the window sill"
        self.assertEqual(ts.shingle_jaccard(a, b), 0.0)

    def test_two_empties_are_identical(self):
        self.assertEqual(ts.shingle_jaccard("", ""), 1.0)

    def test_one_empty_is_zero(self):
        self.assertEqual(ts.shingle_jaccard("something here at all", ""), 0.0)

    def test_near_duplicate_scores_high(self):
        a = "the bills defeated the dolphins behind josh allen at highmark stadium"
        b = "the bills defeated the dolphins behind josh allen at highmark stadium today"
        self.assertGreater(ts.shingle_jaccard(a, b, k=5), 0.5)

    def test_html_is_stripped_before_scoring(self):
        plain = "the bills defeated the dolphins behind josh allen"
        html = "<p>the <b>bills</b> defeated the dolphins behind josh allen</p>"
        self.assertEqual(ts.shingle_jaccard(plain, html), 1.0)

    def test_short_strings_below_k_still_compare(self):
        self.assertEqual(ts.shingle_jaccard("hello world", "hello world", k=5), 1.0)
        self.assertEqual(ts.shingle_jaccard("hello world", "goodbye moon", k=5), 0.0)

    def test_determinism(self):
        a, b = "one two three four five six", "one two three four five seven"
        self.assertEqual(ts.shingle_jaccard(a, b), ts.shingle_jaccard(a, b))


class KeywordSet(unittest.TestCase):
    def test_strips_generic_stopwords_and_short_tokens(self):
        kw = ts.keyword_set("The Bills are in a big game at the stadium")
        self.assertIn("bills", kw)
        self.assertIn("stadium", kw)
        self.assertNotIn("the", kw)   # generic stopword
        self.assertNotIn("a", kw)     # length-1
        self.assertNotIn("are", kw)   # generic stopword

    def test_extra_stopwords_remove_domain_vocabulary(self):
        kw = ts.keyword_set("Bills touchdown quarterback stadium",
                            extra_stopwords=SPORTS_STOPWORDS)
        self.assertIn("bills", kw)
        self.assertIn("stadium", kw)
        self.assertNotIn("touchdown", kw)     # domain stopword removed
        self.assertNotIn("quarterback", kw)


class MaxSimilarityPrefilter(unittest.TestCase):
    def test_empty_corpus(self):
        r = ts.max_similarity("anything", [])
        self.assertEqual((r.score, r.best_index, r.num_compared), (0.0, None, 0))

    def test_finds_the_near_duplicate(self):
        corpus = [
            "the chiefs edged the ravens as patrick mahomes marched down the field in kansas city",
            "the bills defeated the dolphins behind josh allen at highmark stadium in a divisional showdown",
        ]
        cand = "the bills defeated the dolphins behind josh allen at highmark stadium in a divisional showdown today"
        r = ts.max_similarity(cand, corpus, prefilter_stopwords=SPORTS_STOPWORDS)
        self.assertEqual(r.best_index, 1)
        self.assertGreater(r.score, 0.5)

    def test_prefilter_prunes_shared_vocab_prose(self):
        """The load-bearing case: a corpus of same-domain prose that shares heavy
        generic vocabulary must NOT all clear the pre-filter. num_compared must be
        materially smaller than the corpus size."""
        # 6 recaps, all sharing generic football words, all about DIFFERENT teams.
        corpus = [
            "the packers beat the vikings in green bay behind jordan love three touchdowns",
            "the cowboys defeated the giants in dallas as dak prescott threw two scores",
            "the eagles edged the commanders in philadelphia on a late jalen hurts drive",
            "the niners downed the seahawks in santa clara behind brock purdy passing",
            "the lions beat the bears in detroit as jared goff led four scoring drives",
            "the ravens topped the bengals in baltimore behind lamar jackson rushing",
        ]
        # Candidate is about the Chiefs — shares generic football words with all 6,
        # distinctive words (chiefs, mahomes, kansas) with none.
        cand = "the chiefs beat the titans in kansas city as patrick mahomes threw three touchdowns"
        r = ts.max_similarity(cand, corpus, prefilter_stopwords=SPORTS_STOPWORDS)
        self.assertLess(r.num_compared, len(corpus),
                        "pre-filter degenerated to comparing everything")
        self.assertEqual(r.num_compared, 0,
                         "no distinctive-keyword overlap should clear the filter")

    def test_without_domain_stopwords_the_prefilter_overmatches(self):
        """Proves the domain stopwords are doing the work: with them removed, the
        shared generic vocabulary lets unrelated docs clear the filter."""
        corpus = [
            "the packers beat the vikings behind jordan love three touchdowns and a field goal",
        ]
        cand = "the chiefs beat the titans as patrick mahomes threw three touchdowns and a field goal"
        # No domain stopwords: "beat", "touchdowns", "field", "goal", "three" are
        # all distinctive-looking, so the unrelated doc clears the >=2 filter.
        r_naive = ts.max_similarity(cand, corpus)
        self.assertEqual(r_naive.num_compared, 1)
        # With domain stopwords those generic words drop out and nothing clears.
        r_smart = ts.max_similarity(cand, corpus, prefilter_stopwords=SPORTS_STOPWORDS)
        self.assertEqual(r_smart.num_compared, 0)


if __name__ == "__main__":
    unittest.main()
