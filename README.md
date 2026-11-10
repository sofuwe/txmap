# txmap

`txmap` turns messy bank transaction descriptions into clean merchant names.

Bank exports show cryptic text like `MOBIL@  - 4361    _F` or
`POS Purchase Bulk Barn 476 Mississ`. `txmap` maps each one to a readable
merchant name such as `Mobil` or `Bulk Barn`. It learns from a small set of
labelled examples. It first strips out bank-specific noise like store numbers,
dates and reference codes, then finds the closest match among the examples it
knows. It is pure Python and has no dependencies.

Supported banks: **TD Canada Trust** (`td`) and **Meridian Credit Union** (`meridiancu`).

## How it works

```
raw bank exports ──normalize──▶ standard CSV ──map──▶ labels draft ──(you review)──▶ labels.csv
```

### 1. `normalize`: raw exports to a standard CSV

**Input:** one or more CSV exports straight from your bank. Every bank uses
different columns. `txmap` recognises the bank from the file's shape, or you can
pass `--bank`.

| Bank | Export format |
|---|---|
| `td` | No header: `Date, Description, Out, In, Balance` |
| `meridiancu` | Header: `ID, Date, Account Name, Description1, Description2, Description3, Amount, Balance` |

Keep raw exports in `txmap/data/raw/`. Git ignores that folder, except for
`*.example.csv` files.

**Output:** one CSV with the same columns for every bank:

```csv
Bank,TransactionID,Date,Amount
td,MOBIL@  - 4361    _F,2026-09-28,-45.10
meridiancu,POS Purchase Bulk Barn 476 Mississ,2026-11-05,-4.92
```

- `TransactionID` is the raw description from the bank.
- `Amount` is negative for money going out.
- `Date` is `YYYY-MM-DD`.

### 2. `map`: standard CSV to a labels draft

**Input:** the standard CSV from `normalize`.

**Output:** each row's bank and description, with a guessed `MerchantName`:

```csv
Bank,TransactionID,MerchantName
td,MOBIL@  - 4361    _F,Mobil
```

This draft uses the same format as a labels file. Check the guesses, fix any
that are wrong, then copy the rows into `txmap/data/out/labels.csv` to teach the
model. `txmap` never writes to `labels.csv` itself.

The tool also reports descriptions it is unsure about. With `--review`, it writes
just those to a separate CSV so you know where to look.

### Training data

Labelled examples are CSV rows of `Bank,TransactionID,MerchantName`. Any extra
columns are ignored.

- `txmap/data/out/labels.example.csv` is a small sample that is committed to git.
- Your own labels go in `txmap/data/out/labels.csv`. Git ignores this file, so your
  transaction history stays private. When it exists, `txmap` uses it by default;
  otherwise it uses the sample.

To start your own file, copy the sample and add rows:

```sh
cp txmap/data/out/labels.example.csv txmap/data/out/labels.csv
```

You can also pass any labels file with `--labels`.

## Day-to-day commands

Set up the environment (installs Python 3.13 if needed):

```sh
uv sync
```

Normalize raw exports. Pass several files to combine them:

```sh
uv run txmap normalize txmap/data/raw/td-2026-11.csv txmap/data/raw/meridiancu-2026-11.csv -o txmap/data/normalized/all.csv
```

Map them to merchant names, and save the uncertain ones for review:

```sh
uv run txmap map txmap/data/all.csv -o txmap/data/out/draft.csv --review txmap/data/out/review.csv
```

Check accuracy on descriptions the model hasn't seen (`-v` lists the misses):

```sh
uv run txmap eval -v
```

Train a model file once and reuse it, instead of retraining on every run:

```sh
uv run txmap train txmap/data/out/labels.csv -o txmap/data/models/model.json
uv run txmap map txmap/data/normalized/all.csv --model txmap/data/models/model.json
```

Run the tests:

```sh
uv run python -m unittest
```

Add a dependency:

```sh
uv add <package>
```

## Adding a bank

In `txmap/banks.py`:

1. Write a parser that turns the bank's export rows into standard rows.
2. Write a cleaner that strips the bank's noise from descriptions.
3. Register both in `BANKS`.
4. Teach `detect()` to recognise the bank's export.

Add a sample export as `txmap/data/raw/<bank>.example.csv` and a few rows to
`txmap/data/out/labels.example.csv`.
