"""Turn raw bank exports into merchant labels.

Pipeline:
  normalize  raw bank export(s)  -> standard CSV (Bank,TransactionID,Date,Amount)
  map        standard CSV        -> labels draft (Bank,TransactionID,MerchantName)
"""
import argparse
import contextlib
import csv
import os
import sys

from .banks import BANKS, STANDARD_COLUMNS, detect
from .model import Model

DATA_OUT_DIR = os.path.join(os.path.dirname(__file__), "data/out")
EXAMPLE_LABELS = os.path.join(DATA_OUT_DIR, "labels.example.csv")
# Your own labels.csv (git-ignored) is used when present; otherwise the committed sample.
_PRIVATE_LABELS = os.path.join(DATA_OUT_DIR, "labels.csv")
DEFAULT_LABELS = _PRIVATE_LABELS if os.path.exists(_PRIVATE_LABELS) else EXAMPLE_LABELS

MAP_COLUMNS = ["Bank", "TransactionID", "MerchantName"]


def read_labels(path):
    with open(path, newline="") as f:
        return [(r["Bank"], r["TransactionID"], r["MerchantName"]) for r in csv.DictReader(f)]


def read_normalized(path):
    """Yield standard rows from a normalized CSV."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = {"Bank", "TransactionID"} - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"error: {path} is missing {sorted(missing)}; run `txmap normalize` on raw exports first")
        yield from reader


def _open_out(path):
    """Open the output file, or stdout (left open) when no path is given."""
    return open(path, "w", newline="") if path else contextlib.nullcontext(sys.stdout)


def cmd_normalize(args):
    if args.bank and args.bank not in BANKS:
        sys.exit(f"error: unknown bank {args.bank!r}; known: {sorted(BANKS)}")
    with _open_out(args.output) as out:
        w = csv.DictWriter(out, fieldnames=STANDARD_COLUMNS)
        w.writeheader()
        for path in args.inputs:
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            bank = args.bank or detect(rows)
            if not bank:
                sys.exit(f"error: can't tell which bank {path} is from; pass --bank one of {sorted(BANKS)}")
            n = 0
            for row in BANKS[bank]["parse"](rows):
                w.writerow(row)
                n += 1
            print(f"{path}: {n} transactions ({bank})", file=sys.stderr)


def load_model(args):
    if args.model:
        return Model.load(args.model)
    return Model.train(read_labels(args.labels or DEFAULT_LABELS))


def cmd_map(args):
    model = load_model(args)
    review = {}
    with _open_out(args.output) as out:
        w = csv.DictWriter(out, fieldnames=MAP_COLUMNS)
        w.writeheader()
        for row in read_normalized(args.input):
            bank, raw = row["Bank"], row["TransactionID"]
            merchant, conf, src = model.predict(bank, raw)
            w.writerow({"Bank": bank, "TransactionID": raw, "MerchantName": merchant})
            if conf < args.min_confidence:
                review[(bank, raw.strip())] = (merchant, conf, src)
    if review:
        print(f"{len(review)} distinct descriptors below confidence {args.min_confidence}; "
              f"check them before adding to your labels.", file=sys.stderr)
        if args.review:
            with open(args.review, "w", newline="") as f:
                rw = csv.writer(f)
                rw.writerow(["Bank", "TransactionID", "MerchantName", "Confidence"])
                for (bank, raw), (m, c, _) in sorted(review.items()):
                    rw.writerow([bank, raw, m, f"{c:.2f}"])


def cmd_train(args):
    Model.train(read_labels(args.labels)).save(args.output)
    print(f"saved model to {args.output}", file=sys.stderr)


def cmd_eval(args):
    """K-fold over distinct normalized descriptors: measures accuracy on descriptors the model
    has NOT seen (the hard case). Repeats of a seen descriptor are trivially correct."""
    from .banks import clean
    rows = read_labels(args.labels)
    keys = sorted({(b.lower(), clean(b, r)) for b, r, _ in rows})
    fold_of = {k: i % args.folds for i, k in enumerate(keys)}
    correct = total = 0
    wrong = []
    for fold in range(args.folds):
        train = [x for x in rows if fold_of[(x[0].lower(), clean(x[0], x[1]))] != fold]
        test = [x for x in rows if fold_of[(x[0].lower(), clean(x[0], x[1]))] == fold]
        model = Model.train(train)
        for bank, raw, truth in test:
            pred, conf, src = model.predict(bank, raw)
            total += 1
            if pred.casefold() == truth.casefold():
                correct += 1
            else:
                wrong.append((raw.strip(), truth, pred, src))
    print(f"unseen-descriptor accuracy: {correct}/{total} = {correct / total:.1%} "
          f"({len(keys)} distinct descriptors, {args.folds}-fold)")
    if args.verbose:
        for raw, truth, pred, src in wrong:
            print(f"  {raw!r}: expected {truth!r}, got {pred!r} [{src}]")


def main(argv=None):
    p = argparse.ArgumentParser(prog="txmap", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # COMMAND: `normalize`
    #
    n = sub.add_parser("normalize", help="convert raw bank export(s) into one standard CSV "
                                         "(Bank,TransactionID,Date,Amount)")
    n.add_argument("inputs", nargs="+", help="raw export CSV(s); bank is detected from each file's shape")
    n.add_argument("-o", "--output")
    n.add_argument("--bank", help=f"force the bank for all inputs ({', '.join(sorted(BANKS))})")
    n.set_defaults(fn=cmd_normalize)

    # COMMAND: `map`
    #
    m = sub.add_parser("map", help="add MerchantName to a normalized CSV, producing a labels draft")
    m.add_argument("input", help="normalized CSV from `txmap normalize`")
    m.add_argument("-o", "--output")
    m.add_argument("--model", help="trained model JSON (default: train from labels)")
    m.add_argument("--labels", help="labels CSV to train from (default: data/out/labels.csv, else the example)")
    m.add_argument("--review", help="write low-confidence descriptors here for labelling")
    m.add_argument("--min-confidence", type=float, default=0.7)
    m.set_defaults(fn=cmd_map)

    # COMMAND: `train`
    #
    t = sub.add_parser("train", help="train a model from a labels CSV (Bank,TransactionID,MerchantName)")
    t.add_argument("labels")
    t.add_argument("-o", "--output", default="model.json")
    t.set_defaults(fn=cmd_train)

    # COMMAND: `eval`
    #
    e = sub.add_parser("eval", help="cross-validated accuracy on a labels CSV")
    e.add_argument("labels", nargs="?", default=DEFAULT_LABELS)
    e.add_argument("--folds", type=int, default=5)
    e.add_argument("-v", "--verbose", action="store_true")
    e.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    args.fn(args)
    return 0
