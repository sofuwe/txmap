import csv
import os
import tempfile
import unittest

from txmap.banks import clean, detect
from txmap.cli import EXAMPLE_LABELS, main
from txmap.model import Model

TD_RAW = '"2026-07-10","MADINA SPICE      _F","5.88",,"16670.38"\n' \
         '"2026-07-11","MOBILE DEPOSIT",,"100.00","16770.38"\n'

MERIDIAN_RAW = (
    " ID, Date, Account Name, Description1, Description2, Description3, Amount, Balance\n"
    '1,2026-11-05 12:00:00 AM,123-Chequing - 0,"POS Purchase Mobil 4361 Toronto Onca",'
    '"Other Reference # 117061","",-4.92,2253.32\n'
    '2,2026-11-06 12:00:00 AM,123-Chequing - 0,"e-Transfer Out","Service Charge 1.00",'
    '"Other Reference # 1",-901,1352.32\n'
)


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


class CleanMeridian(unittest.TestCase):
    def test_normalization(self):
        cases = {
            "POS Purchase Mobil 4361 Toronto Onca": "MOBIL",           # city stripped
            "POS Purchase Bulk Barn 476 Mississ": "BULK BARN",         # cut-off city stripped
            "POS Purchase Truck 1 North York Onca": "TRUCK",           # two-word city
            "POS Purchase Sh Vending Richmond H": "SH VENDING",
            "Bill Payment CITY OF TORONTO": "CITY OF TORONTO",         # "OF <city>" kept
            "POS Purchase Islamic Society Of Mar": "ISLAMIC SOCIETY OF MAR",  # too short to strip
            "Pre-Authorized I3 INSTITUTE": "I3 INSTITUTE",
            "Bill Payment WYSE METER SOLUTIONS": "WYSE METER SOLUTIONS",
            "e-Transfer Out": "E TRANSFER OUT",
        }
        for raw, want in cases.items():
            self.assertEqual(clean("meridiancu", raw), want, raw)


class ModelTest(unittest.TestCase):
    def test_exact_variants_and_fallback(self):
        m = Model.train([("td", "DOLLARAMA #1348   _F", "Dollarama")])

        merchant_actual, *_ = m.predict("td", "DOLLARAMA #9999   _F")
        self.assertEqual(merchant_actual, "Dollarama")

        merchant_actual, conf_actual, src_actual = m.predict("td", "ZZZ UNKNOWN   _F")
        self.assertEqual((merchant_actual, conf_actual, src_actual), ("Zzz Unknown", 0.0, "fallback"))


def run_cli(content, *args, name="in.csv"):
    """Write content to a temp file, run `txmap <args> <file> -o <out>`, return output rows."""
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, name), os.path.join(d, "out.csv")
        with open(src, "w") as fo:
            fo.write(content)
        main([*args, src, "-o", out])
        with open(out, newline="") as fi:
            return list(csv.reader(fi))


class NormalizeTest(unittest.TestCase):
    def test_detect(self):
        self.assertEqual(detect(list(csv.reader(TD_RAW.splitlines()))), "td")
        self.assertEqual(detect(list(csv.reader(MERIDIAN_RAW.splitlines()))), "meridiancu")
        self.assertIsNone(detect([["something", "else"]]))

    def test_td(self):
        rows = run_cli(TD_RAW, "normalize")
        self.assertEqual(rows, [
            ["Bank", "TransactionID", "Date", "Amount"],
            ["td", "MADINA SPICE      _F", "2026-07-10", "-5.88"],
            ["td", "MOBILE DEPOSIT", "2026-07-11", "100.00"],
        ])

    def test_meridiancu(self):
        rows = run_cli(MERIDIAN_RAW, "normalize")
        self.assertEqual(rows, [
            ["Bank", "TransactionID", "Date", "Amount"],
            ["meridiancu", "POS Purchase Mobil 4361 Toronto Onca", "2026-11-05", "-4.92"],
            ["meridiancu", "e-Transfer Out", "2026-11-06", "-901"],
        ])

    def test_unknown_bank_exits(self):
        with self.assertRaises(SystemExit):
            run_cli("a,b\n1,2\n", "normalize")


class MapTest(unittest.TestCase):
    def test_labels_draft(self):
        normalized = ("Bank,TransactionID,Date,Amount\n"
                      "td,METRO  728        _F,2026-01-01,-9.99\n"
                      "meridiancu,POS Purchase Mobil 4361 Toronto Onca,2026-11-05,-4.92\n")
        rows = run_cli(normalized, "map", "--labels", EXAMPLE_LABELS)
        self.assertEqual(rows, [
            ["Bank", "TransactionID", "MerchantName"],
            ["td", "METRO  728        _F", "Metro"],
            ["meridiancu", "POS Purchase Mobil 4361 Toronto Onca", "Mobil"],
        ])

    def test_rejects_raw_export(self):
        with self.assertRaises(SystemExit):
            run_cli(TD_RAW, "map", "--labels", EXAMPLE_LABELS)


if __name__ == "__main__":
    unittest.main()


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeClient:
    """Stands in for anthropic.Anthropic(); records prompts and returns a fixed merchant."""

    def __init__(self, merchant):
        self.merchant, self.prompts = merchant, []
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        resp = type("R", (), {})()
        resp.stop_reason = "end_turn"
        resp.content = [_FakeBlock('{"merchant": "%s"}' % self.merchant)]
        return resp


class LLMFallback(unittest.TestCase):
    def setUp(self):
        from txmap.llm import LLMNamer
        self.tmp = tempfile.mkdtemp()
        self.client = _FakeClient("Fresh Palace Supermarket")
        self.namer = LLMNamer(cache_path=os.path.join(self.tmp, "cache.json"), client=self.client)
        self.model = Model.train([("meridiancu", "POS Purchase Bulk Barn 476 Mississ", "Bulk Barn")])

    def test_unmatched_descriptor_goes_to_llm_with_examples(self):
        got = self.model.predict("meridiancu", "POS Purchase Fresh Palace Supermark", namer=self.namer)
        self.assertEqual(got, ("Fresh Palace Supermarket", 0.5, "llm"))
        self.assertIn("BULK BARN -> Bulk Barn", self.client.prompts[0])

    def test_matched_descriptor_skips_llm(self):
        got = self.model.predict("meridiancu", "POS Purchase Bulk Barn 476 Mississ", namer=self.namer)
        self.assertEqual(got[2], "exact")
        self.assertEqual(self.client.prompts, [])

    def test_answers_are_cached(self):
        from txmap.llm import LLMNamer
        self.model.predict("meridiancu", "POS Purchase Fresh Palace Supermark", namer=self.namer)
        self.namer.save()
        again = LLMNamer(cache_path=self.namer.cache_path, client=self.client)
        self.model.predict("meridiancu", "POS Purchase Fresh Palace Supermark", namer=again)
        self.assertEqual((len(self.client.prompts), again.calls), (1, 0))

    def test_missing_api_key_exits_with_message(self):
        def no_key(**kw):
            raise TypeError('"Could not resolve authentication method. Expected one of api_key, ..."')
        self.client.create = no_key
        with self.assertRaises(SystemExit) as cm:
            self.model.predict("meridiancu", "POS Purchase Fresh Palace Supermark", namer=self.namer)
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception.code))
