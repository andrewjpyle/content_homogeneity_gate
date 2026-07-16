"""A worked example of a caller-supplied domain-vocabulary stopword set.

The pre-filter in ``text_similarity.max_similarity`` keys on the *distinctive*
tokens of a document — the ones that separate one page from another. In a sports
recap corpus, the generic sports vocabulary ("game", "quarterback", "touchdown")
appears in every single recap, so leaving it in makes every recap look similar to
every other one at the pre-filter stage, and the filter degenerates to "compare
against everything."

Passing this set as ``prefilter_stopwords`` strips that generic vocabulary so the
filter keys on team names, cities, players, and scores — the tokens that actually
distinguish a Bills-Dolphins recap from a Chiefs-Ravens one.

This is illustrative. Build the equivalent set for YOUR domain: the words that
appear in nearly every document you produce and therefore carry no
distinguishing signal.
"""
from __future__ import annotations

SPORTS_STOPWORDS = frozenset({
    # cross-sport generic
    "game", "games", "team", "teams", "season", "win", "wins", "won", "loss",
    "lost", "losses", "defeated", "beat", "victory", "score", "scored", "points",
    "point", "championship", "championships", "playoff", "playoffs", "final",
    "league", "professional", "coach", "coaches", "home", "away", "visiting",
    "record", "led", "lead", "night", "week", "recap", "title",
    "first", "second", "third", "fourth", "half", "period", "quarter",
    # football
    "football", "quarterback", "touchdown", "touchdowns", "yard", "yards",
    "rushing", "passing", "defense", "offense", "interception", "fumble",
    "kickoff", "drive", "possession", "field", "threw", "ran", "caught",
    # baseball
    "baseball", "inning", "innings", "run", "runs", "hit", "hits", "pitch",
    "pitcher", "strikeout", "strikeouts", "homer", "homerun", "rbi", "base",
    # basketball
    "basketball", "rebound", "rebounds", "assist", "assists", "dunk",
    "three", "pointer", "court", "foul", "fouls",
    # hockey
    "hockey", "goal", "goals", "goalie", "puck", "ice", "shot", "shots",
    "powerplay", "penalty",
})
