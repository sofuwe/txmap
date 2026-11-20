"""Plumbing for the behaviour tests: run a command, read a CSV. No txmap logic lives here."""

import csv
import os
import shlex
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "tests" / "behaviour" / "data"

REVIEW_HEADER = ["Bank", "TransactionID", "MerchantName", "Confidence"]


def cmd(line, fails=False):
    """Run `line` from the repo root exactly as a shell would (minus the shell).

    Asserts it succeeds, or that it fails when `fails=True`. Returns the finished
    process: `.returncode`, `.stdout`, `.stderr`. API keys are removed from the
    environment so nothing can reach the network.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
    result = subprocess.run(
        shlex.split(line), cwd=REPO, env=env, capture_output=True, text=True, check=False, timeout=120
    )
    if fails and result.returncode == 0:
        raise AssertionError(f"expected this to fail, but it succeeded:\n  {line}\n{result.stderr}")
    if not fails and result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}:\n  {line}\n{result.stderr}")
    return result


def rows(path):
    """All rows of a CSV (header included). `path` is relative to the repo root."""
    with open(REPO / path, newline="") as f:
        return list(csv.reader(f))


def merchants(path):
    """A labels draft as {(bank, description): merchant}."""
    header, *body = rows(path)
    assert header == ["Bank", "TransactionID", "MerchantName"], header
    return {(bank, raw): merchant for bank, raw, merchant in body}


def review(path):
    """A review file as {(bank, description): (merchant, confidence)}. No file means nothing to review."""
    if not (REPO / path).exists():
        return {}
    header, *body = rows(path)
    assert header == REVIEW_HEADER, header
    return {(bank, raw): (merchant, float(conf)) for bank, raw, merchant, conf in body}


def clear_generated():
    """Delete outputs from earlier runs so a stale file can't make a test pass. Committed inputs are kept."""
    keep = {
        DATA / "normalized": lambda p: p.name == ".gitkeep",
        DATA / "models": lambda p: p.name == ".gitkeep",
        DATA / "out": lambda p: p.name.startswith("labels") and p.suffix == ".csv",
    }
    for folder, is_kept in keep.items():
        folder.mkdir(parents=True, exist_ok=True)
        for p in folder.iterdir():
            if p.is_file() and not is_kept(p):
                p.unlink()


class BehaviourTest(unittest.TestCase):
    def setUp(self):
        clear_generated()
