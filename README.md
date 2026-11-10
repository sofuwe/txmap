# txmap

`txmap` turns messy bank transaction descriptions into clean merchant names.

Bank exports show cryptic text like `MOBIL@  - 4361    _F` or `SQ *MADINA SPICE #12`.
`txmap` maps each one to a readable merchant name such as `Mobil` or `Madina Spice`.
It learns from a small set of labelled examples. It first strips out bank-specific
noise like store numbers, dates and reference codes, then finds the closest
match among the examples it knows. It is pure Python and has no dependencies.

## How it works

### Input

A CSV file of transactions, in one of two forms:

- **A file with a header** that has a `TransactionID` column holding the raw
  description, plus an optional `Bank` column:

  ```csv
  Date,TransactionID,Amount,Bank
  2026-09-28,MOBIL@  - 4361    _F,45.10,td
  ```

  If there is no `Bank` column, pass `--bank`.

- **A raw bank export with no header**, if `--bank` names a supported layout.
  Only `td` (TD Canada Trust chequing) is supported for now:

  ```csv
  09/28/2026,MOBIL@  - 4361    _F,45.10,,1200.00
  ```

### Output

A CSV with one row per transaction. It goes to the screen, or to a file with `-o`:

```csv
TransactionID,MerchantName
MOBIL@  - 4361    _F,Mobil
```

The tool also reports descriptions it is unsure about. With `--review`, it writes
them to a CSV that you can label and add to the training data.

### Training data

Labelled examples are CSV rows of `Bank,TransactionID,MerchantName`.

- `txmap/data/labels.example.csv` is a small sample that is committed to git.
- Your own labels go in `txmap/data/labels.csv`. Git ignores this file, so your
  transaction history stays private. When it exists, `txmap` uses it by default;
  otherwise it uses the sample.

To start your own file, copy the sample and add rows:

```sh
cp txmap/data/labels.example.csv txmap/data/labels.csv
```

You can also pass any labels file with `--labels`.

## Day-to-day commands

Set up the environment (installs Python 3.13 if needed):

```sh
uv sync
```

Map a transactions file to merchant names:

```sh
uv run txmap map transactions.csv --bank td -o mapped.csv
```

Map, and save the uncertain matches so you can label them:

```sh
uv run txmap map transactions.csv --bank td -o mapped.csv --review review.csv
```

Check accuracy on descriptions the model hasn't seen (`-v` lists the misses):

```sh
uv run txmap eval -v
```

Train a model file once and reuse it, instead of retraining on every run:

```sh
uv run txmap train txmap/data/labels.csv -o model.json   # or labels.example.csv
uv run txmap map transactions.csv --bank td --model model.json
```

Run the tests:

```sh
uv run python -m unittest
```

Add a dependency:

```sh
uv add <package>
```
