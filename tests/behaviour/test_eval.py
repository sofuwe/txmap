"""5. Eval: `txmap eval` measures accuracy on descriptions the model hasn't seen.

It holds out part of the labels in turn (cross-validation), so every labelled row
is scored once by a model that never saw its description.

labels-eval.csv is labels.csv plus two rows. "Mystery Co" can't be guessed from
its description, so there's always at least one miss to show.
"""

from .helpers import BehaviourTest, cmd, rows


class Eval(BehaviourTest):
    def test_reports_accuracy_over_every_labelled_row(self):
        result = cmd("uv run txmap eval tests/behaviour/data/out/labels-eval.csv")

        _, *labels = rows("tests/behaviour/data/out/labels-eval.csv")
        self.assertIn("accuracy", result.stdout)
        self.assertRegex(result.stdout, rf"\b\d+/{len(labels)}\b")

    def test_verbose_lists_each_miss_with_expected_and_actual(self):
        quiet = cmd("uv run txmap eval tests/behaviour/data/out/labels-eval.csv")
        verbose = cmd("uv run txmap eval tests/behaviour/data/out/labels-eval.csv -v")

        self.assertNotIn("Mystery Co", quiet.stdout)
        self.assertIn("Mystery Co", verbose.stdout)
        self.assertIn("ZQXW HOLDINGS", verbose.stdout)

    def test_results_are_reproducible(self):
        first = cmd("uv run txmap eval tests/behaviour/data/out/labels-eval.csv -v")
        second = cmd("uv run txmap eval tests/behaviour/data/out/labels-eval.csv -v")

        self.assertEqual(first.stdout, second.stdout)
