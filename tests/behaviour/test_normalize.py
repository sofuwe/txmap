"""1. Normalize: `txmap normalize` turns any supported bank export into one standard CSV.

Standard columns: Bank,TransactionID,Date,Amount. TransactionID is the bank's
description, kept exactly. Amount is negative for money out. Date is YYYY-MM-DD.
"""

import csv
import io

from .helpers import BehaviourTest, cmd, rows

STANDARD_HEADER = ["Bank", "TransactionID", "Date", "Amount"]


def standard(path):
    """Standard rows with amounts as numbers, so `-45.10` and `-45.1` compare equal."""
    header, *body = rows(path)
    assert header == STANDARD_HEADER, header
    return [(bank, raw, date, float(amount)) for bank, raw, date, amount in body]


class Normalize(BehaviourTest):
    def test_td_export_becomes_standard_rows(self):
        """Money out is negative, money in is positive, and descriptions keep their spacing."""
        cmd("uv run txmap normalize tests/behaviour/data/raw/td.csv -o tests/behaviour/data/normalized/td.csv")

        self.assertEqual(
            standard("tests/behaviour/data/normalized/td.csv"),
            [
                ("td", "MOBIL@  - 4361    _F", "2026-09-02", -45.10),
                ("td", "DOLLARAMA #1348   _F", "2026-09-03", -8.47),
                ("td", "DOLLARAMA #9999   _F", "2026-09-04", -3.10),
                ("td", "SHOPPERS DRUG M   _F", "2026-09-05", -12.00),
                ("td", "SHOPPERS DRUG MRT _F", "2026-09-06", -23.15),
                ("td", "ZQXW HOLDINGS   _F", "2026-09-07", -9.99),
                ("td", "ZQXW HOLDINGS   _F", "2026-09-08", -9.99),
                ("td", "MOBILE DEPOSIT", "2026-09-09", 500.00),
            ],
        )

    def test_meridian_export_becomes_standard_rows(self):
        """The first description column is the TransactionID, and timestamps become dates."""
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/meridiancu.csv -o tests/behaviour/data/normalized/meridiancu.csv"
        )

        self.assertEqual(
            standard("tests/behaviour/data/normalized/meridiancu.csv"),
            [
                ("meridiancu", "POS Purchase Mobil 4361 Toronto Onca", "2026-10-01", -40.25),
                ("meridiancu", "POS Purchase Bulk Barn 123 Toronto Onca", "2026-10-02", -12.40),
                ("meridiancu", "POS Purchase Bulk Barn 476 Mississ", "2026-10-03", -6.78),
                ("meridiancu", "POS Purchase Bulk Bar Toronto Onca", "2026-10-04", -8.15),
                ("meridiancu", "e-Transfer Out", "2026-10-05", -100.00),
                ("meridiancu", "Payroll Deposit ACME", "2026-10-15", 1200.50),
            ],
        )

    def test_several_exports_combine_into_one_file_in_the_order_given(self):
        """One header, then each file's rows in turn. Banks can be mixed."""
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/meridiancu.csv tests/behaviour/data/raw/td.csv -o tests/behaviour/data/normalized/all.csv"
        )

        banks = [bank for bank, *_ in standard("tests/behaviour/data/normalized/all.csv")]
        self.assertEqual(banks, ["meridiancu"] * 6 + ["td"] * 8)

    def test_bank_is_detected_so_naming_it_changes_nothing(self):
        cmd("uv run txmap normalize tests/behaviour/data/raw/td.csv -o tests/behaviour/data/normalized/detected.csv")
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/td.csv --bank td -o tests/behaviour/data/normalized/named.csv"
        )

        self.assertEqual(
            rows("tests/behaviour/data/normalized/detected.csv"), rows("tests/behaviour/data/normalized/named.csv")
        )

    def test_without_an_output_path_it_writes_to_stdout(self):
        result = cmd("uv run txmap normalize tests/behaviour/data/raw/td.csv")

        header, *body = csv.reader(io.StringIO(result.stdout))
        self.assertEqual(header, STANDARD_HEADER)
        self.assertEqual(len(body), 8)
        self.assertIn("MOBIL@  - 4361    _F", [raw for _, raw, *_ in body])

    def test_unrecognised_export_fails_and_suggests_naming_the_bank(self):
        result = cmd("uv run txmap normalize tests/behaviour/data/raw/unknown-bank.csv", fails=True)

        self.assertIn("--bank", result.stderr)

    def test_unknown_bank_name_fails_and_lists_the_supported_banks(self):
        result = cmd("uv run txmap normalize tests/behaviour/data/raw/td.csv --bank nosuchbank", fails=True)

        self.assertIn("td", result.stderr)
        self.assertIn("meridiancu", result.stderr)
