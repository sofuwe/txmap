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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .banks import BANKS, STANDARD_COLUMNS, detect
from .llm import DEFAULT_MODEL as LLM_DEFAULT_MODEL
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


def make_namer(args):
    if not args.llm:
        return None
    from .llm import LLMNamer
    return LLMNamer(model=args.llm_model)


def predict_all(model, pairs, namer):
    """Predict [(bank, raw)] in order. LLM calls are slow, so run them in parallel."""
    if not namer:
        return [model.predict(b, r) for b, r in pairs]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda p: model.predict(*p, namer=namer), pairs))
    finally:
        namer.save()


def cmd_map(args):
    model = load_model(args)
    namer = make_namer(args)
    rows = list(read_normalized(args.input))
    preds = predict_all(model, [(r["Bank"], r["TransactionID"]) for r in rows], namer)
    review = {}
    with _open_out(args.output) as out:
        w = csv.DictWriter(out, fieldnames=MAP_COLUMNS)
        w.writeheader()
        for row, (merchant, conf, src) in zip(rows, preds):
            bank, raw = row["Bank"], row["TransactionID"]
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
    namer = make_namer(args)
    correct = total = 0
    wrong = []
    by_src, ok_by_src = Counter(), Counter()
    for fold in range(args.folds):
        train = [x for x in rows if fold_of[(x[0].lower(), clean(x[0], x[1]))] != fold]
        test = [x for x in rows if fold_of[(x[0].lower(), clean(x[0], x[1]))] == fold]
        model = Model.train(train)
        preds = predict_all(model, [(b, r) for b, r, _ in test], namer)
        for (bank, raw, truth), (pred, conf, src) in zip(test, preds):
            total += 1
            by_src[src] += 1
            if pred.casefold() == truth.casefold():
                correct += 1
                ok_by_src[src] += 1
            else:
                wrong.append((raw.strip(), truth, pred, src))
    print(f"unseen-descriptor accuracy: {correct}/{total} = {correct / total:.1%} "
          f"({len(keys)} distinct descriptors, {args.folds}-fold)")
    print("  by source: " + ", ".join(f"{s} {ok_by_src[s]}/{n}" for s, n in by_src.most_common()))
    if namer:
        print(f"  LLM: {namer.calls} API calls ({args.llm_model}); the rest came from the cache")
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
    m.add_argument("--llm", action="store_true",
                   help="name unmatched descriptors with Claude (sends them to the Anthropic API)")
    m.add_argument("--llm-model", default=LLM_DEFAULT_MODEL, help="Claude model for --llm")
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
    e.add_argument("--llm", action="store_true",
                   help="name unmatched descriptors with Claude (sends them to the Anthropic API)")
    e.add_argument("--llm-model", default=LLM_DEFAULT_MODEL, help="Claude model for --llm")
    e.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    args.fn(args)
    return 0
