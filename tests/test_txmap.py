import csv
import io
import os
import tempfile
import unittest

from txmap.banks import clean
from txmap.cli import EXAMPLE_LABELS, main
from txmap.model import Model


class CleanTD(unittest.TestCase):
    def test_normalization(self):
        cases = {
            "DOLLARAMA #1348   _F": "DOLLARAMA",
            "QURANHIVE-    9.00_V": "QURANHIVE",
            "E-TRANSFER ***vtg": "E TRANSFER",
            "UP224 TFR-TO C/C": "UP224 TFR TO C C",  # digits inside a token are kept
            "VESTA  *CHATR     _V": "CHATR",
            "           Wise  MSP": "WISE",
            "TD ATM W/D    005413": "TD ATM W D",
        }
        for raw, want in cases.items():
            self.assertEqual(clean("td", raw), want, raw)


class ModelTest(unittest.TestCase):
    def test_exact_variants_and_fallback(self):
        m = Model.train([("td", "DOLLARAMA #1348   _F", "Dollarama")])

        merchant_actual, *_ = m.predict("td", "DOLLARAMA #9999   _F")
        self.assertEqual(merchant_actual, "Dollarama")
        
        merchant_actual, conf_actual, src_actual = m.predict("td", "ZZZ UNKNOWN   _F")
        self.assertEqual((merchant_actual, conf_actual, src_actual), ("Zzz Unknown", 0.0, "fallback"))


class CliTest(unittest.TestCase):
    def run_map(self, content, *args):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "in.csv"), os.path.join(d, "out.csv")
            with open(src, "w") as fo:
                fo.write(content)
    
            main(["map", src, "-o", out, "--labels", EXAMPLE_LABELS, *args])

            with open(out) as fi:
                return list(csv.reader(fi))

    def test_headerless_td(self):
        rows = self.run_map('"2026-07-10","MADINA SPICE      _F","5.88",,"16670.38"\n', "--bank", "td")
        self.assertEqual(rows, [["TransactionID", "MerchantName"], ["MADINA SPICE      _F", "Madina Spice"]])

    def test_headered_with_bank_column(self):
        rows = self.run_map("Date,TransactionID,Amount,Bank\n2026-01-01,METRO  728        _F,9.99,td\n")
        self.assertEqual(rows[1], ["METRO  728        _F", "Metro"])


if __name__ == "__main__":
    unittest.main()
