"""3. Map: `txmap map` names every row of a standard CSV using a trained model.

The output is a labels draft (Bank,TransactionID,MerchantName): check it, fix
what's wrong, and copy the rows into your labels to teach the model.
"""

import csv
import io
import unittest

from .helpers import REPO, BehaviourTest, cmd, merchants, review, rows

PRIVATE_LABELS = REPO / "txmap/data/out/labels.csv"


class Map(BehaviourTest):
    def setUp(self):
        super().setUp()
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/td.csv tests/behaviour/data/raw/meridiancu.csv -o tests/behaviour/data/normalized/all.csv"
        )
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json")

    def map_all(self):
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv"
        )
        return merchants("tests/behaviour/data/out/draft.csv")

    def test_labelled_description_gets_its_label(self):
        names = self.map_all()

        self.assertEqual(names["td", "DOLLARAMA #1348   _F"], "Dollarama")

    def test_store_numbers_do_not_matter(self):
        """Another branch of a labelled merchant is recognised, even with a cut-off city name."""
        names = self.map_all()

        self.assertEqual(names["td", "DOLLARAMA #9999   _F"], "Dollarama")
        self.assertEqual(names["meridiancu", "POS Purchase Bulk Barn 476 Mississ"], "Bulk Barn")

    def test_same_merchant_is_recognised_across_banks(self):
        """Mobil is only labelled from TD, but a Meridian Mobil purchase still maps to it."""
        names = self.map_all()

        self.assertEqual(names["meridiancu", "POS Purchase Mobil 4361 Toronto Onca"], "Mobil")

    def test_close_but_not_identical_descriptions_match(self):
        """Banks truncate names differently; near-misses still find the right merchant."""
        names = self.map_all()

        self.assertEqual(names["td", "SHOPPERS DRUG MRT _F"], "Shoppers Drug Mart")
        self.assertEqual(names["meridiancu", "POS Purchase Bulk Bar Toronto Onca"], "Bulk Barn")

    def test_unknown_description_still_gets_a_readable_name(self):
        """With no match, the guess comes from the description itself, without the bank's noise."""
        names = self.map_all()

        guess = names["td", "ZQXW HOLDINGS   _F"]
        self.assertIn("zqxw", guess.casefold())
        self.assertNotIn("_F", guess)

    def test_draft_has_one_row_per_input_row_in_order_with_descriptions_verbatim(self):
        """Duplicates are kept and whitespace isn't touched, so the draft lines up with the input."""
        self.map_all()

        _, *draft = rows("tests/behaviour/data/out/draft.csv")
        _, *standard = rows("tests/behaviour/data/normalized/all.csv")
        self.assertEqual([(bank, raw) for bank, raw, _ in draft], [(bank, raw) for bank, raw, *_ in standard])

    def test_draft_is_a_valid_labels_file(self):
        """Accepting a draft as-is and training on it gives the same names back, all confidently."""
        first = self.map_all()
        cmd("uv run txmap train tests/behaviour/data/out/draft.csv -o tests/behaviour/data/models/from-draft.json")

        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/from-draft.json -o tests/behaviour/data/out/draft-again.csv --review tests/behaviour/data/out/review.csv"
        )

        self.assertEqual(merchants("tests/behaviour/data/out/draft-again.csv"), first)
        self.assertEqual(review("tests/behaviour/data/out/review.csv"), {})

    def test_without_an_output_path_it_writes_to_stdout(self):
        result = cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json"
        )

        header, *body = csv.reader(io.StringIO(result.stdout))
        self.assertEqual(header, ["Bank", "TransactionID", "MerchantName"])
        self.assertIn(["td", "DOLLARAMA #1348   _F", "Dollarama"], body)

    def test_raw_bank_export_is_rejected_with_a_hint_to_normalize_first(self):
        result = cmd(
            "uv run txmap map tests/behaviour/data/raw/td.csv --model tests/behaviour/data/models/model.json",
            fails=True,
        )

        self.assertIn("normalize", result.stderr)

    def test_never_writes_the_private_labels_file(self):
        """Only you edit txmap/data/out/labels.csv; drafts go wherever -o says."""
        before = PRIVATE_LABELS.stat().st_mtime_ns if PRIVATE_LABELS.exists() else None

        self.map_all()

        after = PRIVATE_LABELS.stat().st_mtime_ns if PRIVATE_LABELS.exists() else None
        self.assertEqual(after, before)

    # Planned: `--model` becomes required for `map`, with no more training on the fly (.claude/prompts.md).
    # Remove the decorators once that lands; until then these report as expected failures.

    @unittest.expectedFailure
    def test_model_is_required_and_the_error_points_to_train(self):
        result = cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv -o tests/behaviour/data/out/draft.csv",
            fails=True,
        )

        self.assertIn("train", result.stderr)

    @unittest.expectedFailure
    def test_labels_are_not_accepted_by_map(self):
        """Train first; `map` only reads a model."""
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json --labels tests/behaviour/data/out/labels.csv",
            fails=True,
        )
