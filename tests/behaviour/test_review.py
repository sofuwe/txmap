"""4. Review: `map --review` lists the guesses worth checking before you add them to your labels.

Review columns: Bank,TransactionID,MerchantName,Confidence. A guess is uncertain
when its confidence is below `--min-confidence` (default 0.7).
"""

from .helpers import BehaviourTest, cmd, review, rows

UNKNOWN = ("td", "ZQXW HOLDINGS   _F")
NEAR_MISS = ("td", "SHOPPERS DRUG MRT _F")


class Review(BehaviourTest):
    def setUp(self):
        super().setUp()
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/td.csv tests/behaviour/data/raw/meridiancu.csv -o tests/behaviour/data/normalized/all.csv"
        )
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json")

    def labelled(self):
        _, *labels = rows("tests/behaviour/data/out/labels.csv")
        return {(bank, raw) for bank, raw, _ in labels}

    def test_only_uncertain_guesses_are_listed(self):
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv --review tests/behaviour/data/out/review.csv"
        )

        listed = review("tests/behaviour/data/out/review.csv")
        self.assertIn(UNKNOWN, listed)
        self.assertFalse(self.labelled() & set(listed), "labelled descriptions are never uncertain")
        for key, (merchant, confidence) in listed.items():
            self.assertLess(confidence, 0.7, key)
            self.assertTrue(merchant, key)

    def test_each_description_is_listed_once(self):
        """ZQXW HOLDINGS appears twice in the TD export, but you only need to check it once."""
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv --review tests/behaviour/data/out/review.csv"
        )

        _, *listed = rows("tests/behaviour/data/out/review.csv")
        self.assertEqual([(bank, raw) for bank, raw, *_ in listed].count(UNKNOWN), 1)

    def test_uncertain_guesses_are_flagged_even_without_a_review_file(self):
        result = cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv"
        )

        self.assertIn("confidence", result.stderr)

    def test_min_confidence_moves_the_cutoff(self):
        """At 1, anything short of a sure match is listed; at 0, nothing is."""
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv --review tests/behaviour/data/out/review-default.csv"
        )
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv --review tests/behaviour/data/out/review-strict.csv --min-confidence 1"
        )
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv --review tests/behaviour/data/out/review-lax.csv --min-confidence 0"
        )

        default = set(review("tests/behaviour/data/out/review-default.csv"))
        strict = set(review("tests/behaviour/data/out/review-strict.csv"))
        lax = set(review("tests/behaviour/data/out/review-lax.csv"))
        self.assertIn(NEAR_MISS, strict - default, "a near-miss is fine by default but not at 1")
        self.assertIn(UNKNOWN, strict)
        self.assertFalse(self.labelled() & strict, "labelled descriptions are sure matches")
        self.assertLessEqual(default, strict)
        self.assertEqual(lax, set())
