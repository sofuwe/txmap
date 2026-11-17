"""Character n-gram TF-IDF nearest-neighbour classifier (pure stdlib).

Trained on (bank, raw descriptor, merchant) examples. Predicts by exact normalized
match, then cosine similarity over char trigrams, then (optionally) an LLM given the
nearest labels as examples, then falls back to the cleaned descriptor in title case.
Anything past similarity is flagged low confidence so it can be reviewed/labelled.
"""
import json
import math
from collections import Counter, defaultdict

from .banks import clean

THRESHOLD = 0.7
SAME_BANK_BONUS = 0.05
NUM_EXAMPLES = 10      # nearest labels shown to the LLM fallback
LLM_CONFIDENCE = 0.5   # below the default review threshold, so LLM guesses get reviewed


def _grams(key: str) -> Counter:
    s = "^" + key
    return Counter(s[i:i + 3] for i in range(max(1, len(s) - 2)))


class Model:
    def __init__(self, entries=None):
        self.entries = entries or []  # [{"bank","key","merchant"}]
        self._build()

    @classmethod
    def train(cls, rows):
        """rows: iterable of (bank, raw_descriptor, merchant)."""
        votes = defaultdict(Counter)
        for bank, raw, merchant in rows:
            votes[(bank.lower(), clean(bank, raw))][merchant] += 1
        return cls([{"bank": b, "key": k, "merchant": c.most_common(1)[0][0]}
                    for (b, k), c in sorted(votes.items())])

    def _build(self):
        self.exact = {(e["bank"], e["key"]): e["merchant"] for e in self.entries}
        any_bank = defaultdict(Counter)
        for e in self.entries:
            any_bank[e["key"]][e["merchant"]] += 1
        self.exact_any = {k: c.most_common(1)[0][0] for k, c in any_bank.items()}
        grams = [_grams(e["key"]) for e in self.entries]
        df = Counter(g for gs in grams for g in gs)
        n = len(grams) or 1
        self.idf = {g: math.log((1 + n) / (1 + d)) + 1 for g, d in df.items()}
        self.vecs = [self._vec(gs) for gs in grams]

    def _vec(self, gs: Counter) -> dict:
        v = {g: c * self.idf.get(g, 1.0) for g, c in gs.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}

    def predict(self, bank: str, raw: str, namer=None):
        """Returns (merchant, confidence, source). `namer` (an llm.LLMNamer) handles
        descriptors with no close match; without it they fall back to title case."""
        bank, key = bank.lower(), clean(bank, raw)
        if (bank, key) in self.exact:
            return self.exact[(bank, key)], 1.0, "exact"
        if key in self.exact_any:
            return self.exact_any[key], 0.95, "exact-other-bank"
        ranked = self._ranked(bank, key)
        if ranked and ranked[0][0] >= THRESHOLD:
            best_score, best = ranked[0]
            return best["merchant"], min(best_score, 0.99), "similar"
        if namer:
            examples = [(e["bank"], e["key"], e["merchant"]) for _, e in ranked[:NUM_EXAMPLES]]
            merchant = namer.name(bank, raw, key, examples)
            if merchant:
                return merchant, LLM_CONFIDENCE, "llm"
        return key.title() or raw.strip(), 0.0, "fallback"

    def _ranked(self, bank: str, key: str):
        """All entries as (score, entry), most similar first."""
        q = self._vec(_grams(key))
        scored = []
        for e, v in zip(self.entries, self.vecs):
            score = sum(w * v.get(g, 0.0) for g, w in q.items())
            if e["bank"] == bank:
                score += SAME_BANK_BONUS
            scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return scored

    def save(self, path):
        with open(path, "w") as f:
            json.dump({"entries": self.entries}, f, indent=1)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls(json.load(f)["entries"])
