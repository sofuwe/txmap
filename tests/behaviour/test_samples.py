"""6. Shipped samples: the *.example.* files in txmap/data/ agree with each other and back up the README demo.

These read the committed samples and write only to tests/behaviour/data/.
"""

from .helpers import BehaviourTest, cmd, merchants, rows


class Samples(BehaviourTest):
    def test_normalizing_the_sample_exports_reproduces_the_sample_standard_csv(self):
        cmd(
            "uv run txmap normalize txmap/data/raw/meridiancu.example.csv txmap/data/raw/td.example.csv -o tests/behaviour/data/normalized/samples.csv"
        )

        self.assertEqual(
            rows("tests/behaviour/data/normalized/samples.csv"), rows("txmap/data/normalized/all.example.csv")
        )

    def test_sample_model_is_up_to_date_with_the_sample_labels(self):
        """model.example.json names things exactly as a model freshly trained on labels.example.csv does."""
        cmd("uv run txmap train txmap/data/out/labels.example.csv -o tests/behaviour/data/models/fresh.json")

        cmd(
            "uv run txmap map txmap/data/normalized/all.example.csv --model txmap/data/models/model.example.json -o tests/behaviour/data/out/draft-shipped.csv"
        )
        cmd(
            "uv run txmap map txmap/data/normalized/all.example.csv --model tests/behaviour/data/models/fresh.json -o tests/behaviour/data/out/draft-fresh.csv"
        )

        self.assertEqual(
            rows("tests/behaviour/data/out/draft-shipped.csv"), rows("tests/behaviour/data/out/draft-fresh.csv")
        )

    def test_readme_demo_mobil_from_both_banks(self):
        """README: TD's `MOBIL@  - 4361    _F` and Meridian's `POS Purchase Mobil 4361 Toronto Onca` are both Mobil."""
        cmd(
            "uv run txmap map txmap/data/normalized/all.example.csv --model txmap/data/models/model.example.json -o tests/behaviour/data/out/draft.csv"
        )

        names = merchants("tests/behaviour/data/out/draft.csv")
        self.assertEqual(names["td", "MOBIL@  - 4361    _F"], "Mobil")
        self.assertEqual(names["meridiancu", "POS Purchase Mobil 4361 Toronto Onca"], "Mobil")
