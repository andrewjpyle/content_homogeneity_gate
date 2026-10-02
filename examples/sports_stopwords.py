"""A worked example of a caller-supplied domain-vocabulary stopword set.

The pre-filter in ``text_similarity.max_similarity`` keys on the *distinctive*
tokens of a document: the ones that separate one page from another. In a sports
recap corpus, the generic sports vocabulary ("game", "quarterback", "touchdown")
appears in every single recap, so leaving it in makes every recap look similar to
every other one at the pre-filter stage, and the filter degenerates to "compare
against everything."

Passing this set as ``prefilter_stopwords`` strips that generic vocabulary so the
filter keys on team names, cities, players, and scores, the tokens that actually
distinguish a Bills-Dolphins recap from a Chiefs-Ravens one.

This is illustrative. Build the equivalent set for YOUR domain from a written
list of the vocabulary every page in the domain uses, even pages that are
genuinely different from each other.

Do NOT derive it by counting the most frequent words in your own generated
output. In a templated corpus the most frequent words ARE the template, and
stripping them is how a pre-filter goes blind to the exact pages the gate
exists to catch. (The gate's template rescue now catches that case, see
``DEFAULT_PREFILTER_RESCUE_RATIO``, but a list built from your own output still
throws away the signal the pre-filter needs.)
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
