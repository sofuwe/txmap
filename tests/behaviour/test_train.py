"""2. Train: `txmap train` turns a labels CSV (Bank,TransactionID,MerchantName) into a reusable model file."""

from .helpers import REPO, BehaviourTest, cmd, merchants, rows


class Train(BehaviourTest):
    def test_training_is_deterministic(self):
        """The same labels always give the same model file, byte for byte."""
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/first.json")
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/second.json")

        first = (REPO / "tests/behaviour/data/models/first.json").read_bytes()
        second = (REPO / "tests/behaviour/data/models/second.json").read_bytes()
        self.assertEqual(first, second)

    def test_trained_model_gives_every_labelled_description_its_label(self):
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/td.csv tests/behaviour/data/raw/meridiancu.csv -o tests/behaviour/data/normalized/all.csv"
        )
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json")

        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv"
        )

        names = merchants("tests/behaviour/data/out/draft.csv")
        _, *labels = rows("tests/behaviour/data/out/labels.csv")
        for bank, raw, merchant in labels:
            self.assertEqual(names[bank, raw], merchant, raw)
