import argparse
import csv
import os
import sys

from .banks import LAYOUTS
from .model import Model

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
EXAMPLE_LABELS = os.path.join(DATA_DIR, "labels.example.csv")
# Your own labels.csv (git-ignored) is used when present; otherwise the committed sample.
_PRIVATE_LABELS = os.path.join(DATA_DIR, "labels.csv")
DEFAULT_LABELS = _PRIVATE_LABELS if os.path.exists(_PRIVATE_LABELS) else EXAMPLE_LABELS


def read_labels(path):
    with open(path, newline="") as f:
        return [(r["Bank"], r["TransactionID"], r["MerchantName"]) for r in csv.DictReader(f)]


def read_transactions(path, default_bank):
    """Yield (bank, raw_descriptor). Accepts a headered file (Date,TransactionID,Amount[,Bank])
    or a headerless bank export when --bank names a known layout (e.g. td)."""
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = [c.strip().lower() for c in rows[0]]
    if "transactionid" in header:
        i, b = header.index("transactionid"), header.index("bank") if "bank" in header else None
        for r in rows[1:]:
            bank = r[b] if b is not None else default_bank
            if not bank:
                sys.exit("error: no Bank column and no --bank given")
            yield bank, r[i]
    else:
        if default_bank not in LAYOUTS:
            sys.exit(f"error: headerless file needs --bank one of {sorted(LAYOUTS)}")
        i = LAYOUTS[default_bank]["descriptor"]
        for r in rows:
            if r:
                yield default_bank, r[i]


def load_model(args):
    if args.model:
        return Model.load(args.model)
    return Model.train(read_labels(args.labels or DEFAULT_LABELS))


def cmd_map(args):
    model = load_model(args)
    out = open(args.output, "w", newline="") if args.output else sys.stdout
    w = csv.writer(out)
    w.writerow(["TransactionID", "MerchantName"])
    review = {}
    for bank, raw in read_transactions(args.input, args.bank):
        merchant, conf, src = model.predict(bank, raw)
        w.writerow([raw, merchant])
        if conf < args.min_confidence:
            review[(bank, raw.strip())] = (merchant, conf, src)
    if args.output:
        out.close()
    if review:
        print(f"{len(review)} distinct descriptors below confidence {args.min_confidence}; "
              f"add them to a labels file to improve results.", file=sys.stderr)
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
    p = argparse.ArgumentParser(prog="txmap", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("map", help="write TransactionID,MerchantName CSV for an input CSV")
    m.add_argument("input")
    m.add_argument("-o", "--output")
    m.add_argument("--bank", help="bank for files with no Bank column (e.g. td)")
    m.add_argument("--model", help="trained model JSON (default: train from bundled labels)")
    m.add_argument("--labels", help="labels CSV to train from instead of the bundled one")
    m.add_argument("--review", help="write low-confidence descriptors here for labelling")
    m.add_argument("--min-confidence", type=float, default=0.7)
    m.set_defaults(fn=cmd_map)

    t = sub.add_parser("train", help="train a model from a labels CSV (Bank,TransactionID,MerchantName)")
    t.add_argument("labels")
    t.add_argument("-o", "--output", default="model.json")
    t.set_defaults(fn=cmd_train)

    e = sub.add_parser("eval", help="cross-validated accuracy on a labels CSV")
    e.add_argument("labels", nargs="?", default=DEFAULT_LABELS)
    e.add_argument("--folds", type=int, default=5)
    e.add_argument("-v", "--verbose", action="store_true")
    e.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    args.fn(args)
    return 0
