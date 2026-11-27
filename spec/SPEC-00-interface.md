# Spec: txmap Public Interface — V1

Status: approved (describes the code at `cccb5d5`; no code changes)

## Objective

Write down what `txmap` promises its users today, as one reference. It does not
propose any change. Later changes, such as the planned `map --model`-required
contract in [SPEC-01-behaviour-tests.md](./SPEC-01-behaviour-tests.md), get delta
specs against this file. Once a change ships, it is folded back in here.

This spec serves [MISSION.md](./MISSION.md). It records the stable, tested
public contract that the mission's fourth principle relies on.

**Who it's for:**

- The maintainer, who needs to tell an intended change from an accidental break.
- A contributor, who needs to know what they must keep stable.
- Anyone writing a delta spec, who needs the "Current Behavior" section to link to.

**What counts as public interface:**

1. The `txmap` command: subcommands, arguments, defaults, stdout and stderr, and exit codes.
2. The file formats it reads and writes: raw bank exports, the standard CSV,
   labels, the draft, the review CSV, `model.json` and the LLM cache.
3. Default file locations and environment variables.
4. What `--llm` sends to the Anthropic API.

**Not public:** all Python code. That includes every module, function and
constant (`Model`, `clean`, `BANKS`, `detect`, `THRESHOLD`, …) and the way banks
are added. It is internal and can change freely as long as items 1–4 hold.

Where today's behaviour is surprising or rough, this spec still records it as a
promise, under [Edge-case behaviour](#edge-case-behaviour). Changing any of it
is a behaviour change and needs its own delta spec.

## Tech Stack

- Python ≥ 3.13 (`.python-version`), packaged with hatchling and run with `uv`.
- Core: standard library only, with no runtime dependencies.
- Optional extra `llm`: `anthropic` (`uv sync --extra llm`).
- Dev: `ruff` (line length 120, target py313).

## Commands

```sh
uv sync                                   # core
uv sync --extra llm                       # adds anthropic for --llm
uv run txmap --help                       # or: uv run python -m txmap --help
uv run python -m unittest                 # all tests (unit + behaviour)
uv run python -m unittest discover -s tests/behaviour -t . -v   # behaviour contract only
uv run ruff check . && uv run ruff format --check
```

## Project Structure

```
txmap/cli.py        → the CLI (entry point `txmap = txmap.cli:main`; also `python -m txmap`)
txmap/banks.py      → bank parsers, cleaners, export detection (internal)
txmap/model.py      → nearest-neighbour model and prediction cascade (internal)
txmap/llm.py        → optional Claude namer and its cache (internal)
txmap/data/raw/         → raw exports            (git-ignored except *.example.csv)
txmap/data/normalized/  → standard CSVs          (git-ignored except all.example.csv)
txmap/data/out/         → labels, drafts, review (git-ignored except labels.example.csv)
txmap/data/models/      → model.json, llm-cache.json (git-ignored except model.example.json)
tests/test_txmap.py     → unit tests of internals
tests/behaviour/        → black-box tests of this contract (see spec/SPEC-01-behaviour-tests.md)
spec/                   → specs, numbered in order: this file (the base spec) and SPEC-NN-<change>.md delta specs
tasks/                  → plans and task lists that implement a spec
```

---

## Interface

### Entry points and global conventions

| Convention | Current behaviour |
|---|---|
| Invocation | `txmap <command> …` or `python -m txmap <command> …`. There is no `--version`. |
| Commands | `normalize`, `map`, `train`, `eval`. A command is required. |
| Data output | Goes to `-o/--output` when given. `normalize` and `map` write to stdout when it's omitted. `eval` always writes its report to stdout. |
| Status and diagnostics | Always go to stderr, so piping stdout gives clean CSV. |
| Exit code 0 | Success. |
| Exit code 1 | A handled error. The message starts with `error:` and says how to fix it. Unhandled exceptions (see [Edge-case behaviour](#edge-case-behaviour)) also exit 1, with a traceback. |
| Exit code 2 | Usage error from argparse: unknown command or flag, or a missing required argument. |
| CSV files | Read and written with Python's `csv` module, using the default system encoding and `newline=""`. The header row is required wherever columns are named. |
| Paths | Taken relative to the current directory, except the built-in defaults (labels and LLM cache), which are relative to the installed `txmap/` package. |

### `txmap normalize`

Converts one or more raw bank exports into one standard CSV.

```
txmap normalize INPUT [INPUT ...] [-o OUTPUT] [--bank {meridiancu,td}]
```

| Argument | Meaning |
|---|---|
| `INPUT…` | One or more raw export CSVs. Each file's bank is detected on its own. |
| `-o, --output` | Output path (default: stdout). |
| `--bank` | Treat **every** input as this bank and skip detection. |

**Behaviour**

- Writes one header, `Bank,TransactionID,Date,Amount`, then each file's rows,
  in the order the files were given and the order rows appear within each file.
- After each file, prints `<path>: <n> transactions (<bank>)` to stderr.
- Blank lines in an export are skipped.
- An unknown `--bank` value exits 1 before reading anything, with
  `error: unknown bank '<x>'; known: ['meridiancu', 'td']`.
- A file whose bank can't be detected (and no `--bank`) exits 1 with
  `error: can't tell which bank <path> is from; pass --bank one of ['meridiancu', 'td']`.

### `txmap map`

Gives every row of a standard CSV a `MerchantName`, producing a labels draft.

```
txmap map INPUT [-o OUTPUT] [--model MODEL | --labels LABELS] [--review REVIEW]
          [--min-confidence F] [--llm] [--llm-model NAME]
```

| Argument | Default | Meaning |
|---|---|---|
| `INPUT` | — | Standard CSV. Must have `Bank` and `TransactionID` columns. Other columns are ignored. |
| `-o, --output` | stdout | Draft path. |
| `--model` | none | A trained `model.json`. When given, `--labels` is ignored. |
| `--labels` | [default labels](#default-labels) | Labels CSV to train a model from, on the fly, when there is no `--model`. |
| `--review` | none | Path for the review CSV. |
| `--min-confidence` | `0.7` | Guesses with confidence **strictly below** this count as uncertain. |
| `--llm` | off | Ask Claude to name descriptors that have no close match. See [LLM step](#llm-step---llm). |
| `--llm-model` | `claude-opus-5-5` | Claude model used for `--llm`. |

**Behaviour**

- The draft has the columns `Bank,TransactionID,MerchantName` and exactly one
  row per input row, in input order. `Bank` and `TransactionID` are copied
  through unchanged, whitespace and duplicates included. A draft is a valid labels file.
- Every row gets a non-empty name. See [Prediction contract](#prediction-contract).
- **Uncertain guesses** are those with confidence < `--min-confidence`. They are
  grouped by `(Bank, TransactionID with surrounding whitespace removed)`. If any
  exist, stderr gets:
  `<n> distinct descriptors below confidence <F>; check them before adding to your labels.`
  This happens whether or not `--review` is given.
- With `--review`, the review CSV gets the columns
  `Bank,TransactionID,MerchantName,Confidence`. It has one row per distinct
  uncertain descriptor, sorted by `(Bank, TransactionID)`. `TransactionID` has
  surrounding whitespace removed, and `Confidence` has 2 decimals.
- An input without `Bank` or `TransactionID` (for example a raw export) exits 1 with
  `error: <path> is missing [...]; run `txmap normalize` on raw exports first`.
- `map` never writes `txmap/data/out/labels.csv`.

### `txmap train`

Trains a model from labels and saves it.

```
txmap train LABELS [-o OUTPUT]
```

| Argument | Default | Meaning |
|---|---|---|
| `LABELS` | — (required) | Labels CSV. |
| `-o, --output` | `model.json` in the current directory | Model path. |

**Behaviour:** writes `model.json` and prints `saved model to <path>` to stderr.
Training is deterministic: the same labels always give a byte-identical file.
After training, every labelled description maps back to its own label. The one
exception is conflicting labels; see [Labels](#labels-banktransactionidmerchantname).

### `txmap eval`

Measures accuracy on descriptors the model has **not** seen, using k-fold cross-validation.

```
txmap eval [LABELS] [--folds K] [-v] [--llm] [--llm-model NAME]
```

| Argument | Default | Meaning |
|---|---|---|
| `LABELS` | [default labels](#default-labels) | Labels CSV to evaluate. |
| `--folds` | `5` | Number of folds. |
| `-v, --verbose` | off | List every miss. |
| `--llm`, `--llm-model` | off, `claude-opus-5-5` | Same as `map`. |

**Behaviour**

- Folds are built over distinct `(bank, cleaned key)` descriptors, so all rows
  with the same descriptor are held out together. Every label row is scored
  exactly once. Without `--llm`, the output is the same on every run.
- A prediction counts as correct when it matches the label ignoring case.
- The report goes to stdout:

  ```
  unseen-descriptor accuracy: <correct>/<rows> = <p>% (<distinct> distinct descriptors, <K>-fold)
    by source: <source> <ok>/<n>, ...            # most frequent source first
    LLM: <calls> API calls (<model>); the rest came from the cache    # only with --llm
    '<raw>': expected '<truth>', got '<pred>' [<source>]               # only with -v, one per miss
  ```

  `<source>` is one of `exact`, `exact-other-bank`, `similar`, `llm` or `fallback`.
  Accuracy figures are tuning results, not part of the contract. The format of
  the report is.

### Default labels

When a command takes labels but none are given, it uses
`txmap/data/out/labels.csv` (inside the package) if that file exists, and
otherwise the committed `txmap/data/out/labels.example.csv`. The choice is made
when the program starts. As a result, `eval` and on-the-fly `map` give different
results on different machines.

---

### File formats

#### Raw exports (input to `normalize`)

| Bank id | Detected when | Columns | How rows become standard rows |
|---|---|---|---|
| `td` (TD Canada Trust) | The first row has exactly 5 cells and the first cell is `YYYY-MM-DD`. | No header: `Date, Description, Out, In, Balance` | `TransactionID` = Description, unchanged. `Date` = Date with surrounding whitespace removed. `Amount` = `-<Out>` if Out is non-empty, otherwise `In`. Values are copied as text and not reformatted. |
| `meridiancu` (Meridian Credit Union) | The first row contains `description1` and `account name` (matching ignores case and surrounding whitespace). | Header: `ID, Date, Account Name, Description1, Description2, Description3, Amount, Balance` | Columns are found by header name, ignoring case and spaces. `TransactionID` = Description1 with surrounding whitespace removed. `Date` = the first word of Date (`2026-11-06 12:00:00 AM` → `2026-11-06`). `Amount` = Amount with surrounding whitespace removed (already signed). |

The Meridian check runs before the TD check.

#### Standard CSV (output of `normalize`, input to `map`)

```csv
Bank,TransactionID,Date,Amount
td,MOBIL@  - 4361    _F,2026-09-28,-45.10
```

`Bank` is a bank id. `TransactionID` is the raw bank description, not an ID.
`Amount` is negative for money going out. `map` only reads `Bank` and `TransactionID`.

#### Labels (`Bank,TransactionID,MerchantName`)

- Input to `train`, `eval`, and `map --labels`. The three columns are required
  and any extra columns are ignored. The draft from `map` has this format.
- `Bank` is matched ignoring case. A bank that isn't registered is accepted, and
  its descriptions are cleaned with the generic cleaner.
- Rows with the same `(bank, cleaned descriptor)` are merged by majority vote.
  A tie goes to the merchant that appears first in the file.

#### Draft and review CSVs

Described under [`txmap map`](#txmap-map).

#### `model.json`

```json
{"entries": [{"bank": "td", "key": "MOBIL", "merchant": "Mobil"}, ...]}
```

Each entry is one distinct `(bank, cleaned key)` with its winning merchant.
Entries are sorted by `(bank, key)` and the file is written with `indent=1`.
`key` is the output of the bank's cleaner. A saved model is therefore only
correct for the cleaner version that produced it (see [Edge-case behaviour](#edge-case-behaviour)).
`model.example.json` is equal to `train labels.example.csv`.

#### LLM cache (`txmap/data/models/llm-cache.json`)

This is a JSON object that maps `v<PROMPT_VERSION>|<model>|<bank>|<raw, whitespace removed>`
to a merchant name or `null`. It is written with sorted keys. It is internal,
but it is a file on the user's disk, so where it lives and what it contains
matter for privacy.

---

### Prediction contract

For each `(bank, description)`, the model returns a merchant name, a confidence
in `[0, 1]`, and a source. The cascade order and the confidence *bands* are part
of the contract, because the review flow depends on them. The exact scores and
the cleaning rules are tuning:

| Order | Source | When | Confidence |
|---|---|---|---|
| 1 | `exact` | The cleaned key and bank match a label. | `1.0` |
| 2 | `exact-other-bank` | The cleaned key matches a label from another bank. | `0.95` |
| 3 | `similar` | The best similarity score is at least `0.7`. | That score, capped at `0.99` |
| 4 | `llm` | `--llm` is on and Claude returns a name. | `0.5`, always below the default review cutoff |
| 5 | `fallback` | Otherwise. | `0.0`; the name is the cleaned key in title case, or the stripped raw description if the key is empty |

Promises that follow from this:

- Noise such as store numbers, dates, amounts, reference codes, processor
  prefixes and Meridian city suffixes doesn't change the match.
- The same merchant is recognised across banks.
- At the default cutoff, an exact match is never sent to review, and a guess
  from the LLM or the fallback always is.
- `--min-confidence 0` sends nothing to review. `--min-confidence 1` sends
  everything except `exact` matches.

### LLM step (`--llm`)

- **Requirements:** the `anthropic` package and `ANTHROPIC_API_KEY`.
- **What is sent:** only for descriptions that reach step 4. Each request sends
  the bank, the raw description (whitespace removed), the cleaned key, and the
  10 nearest labels as `bank | key -> merchant`. Nothing is sent without `--llm`.
- **Concurrency:** up to 8 requests at a time.
- **Caching:** each `(prompt version, model, bank, description)` is sent at
  most once, and later runs reuse the cached answer. Refusals and truncated
  answers aren't cached and fall through to `fallback`. An empty answer is
  cached as `null`.
- **Cache write:** when `map --llm` or `eval --llm` finishes, the cache is always
  written to `txmap/data/models/llm-cache.json`, even if no request was made. It
  is also written when the run fails partway. There is no option to choose
  another path.
- **Errors (exit 1):**
  - Missing package: `error: --llm needs the anthropic package; run `uv sync --extra llm``
  - Missing key: `error: --llm needs an Anthropic API key. Set ANTHROPIC_API_KEY …`
  - Rejected key (401): `error: the Anthropic API rejected your API key (401). Check ANTHROPIC_API_KEY.`

  Any other API error exits with a traceback.

### Supported banks

The bank ids `td` and `meridiancu`, and the export layouts above, are public.
How a bank is implemented is internal. Adding a bank adds a new valid `--bank`
value and `Bank` value. It must not change how the existing banks are detected,
parsed or matched.

### Edge-case behaviour

These are promises like everything else in this spec, even where they look
rough. Changing any of them needs a delta spec.

1. `normalize` writes output as it goes. If file 2 of 3 can't be detected, the
   `-o` file is left holding only the rows from file 1.
2. If no guess is uncertain, `map --review PATH` does not create or empty
   `PATH`, so a review file from an earlier run is left in place.
3. When `--model` and `--labels` are both given, `--labels` is silently ignored.
4. Unhandled tracebacks (exit 1) occur for: a missing input, model or labels
   file; a labels file without the three columns; `eval` on an empty labels file
   (division by zero); `--folds 0`; and API errors other than authentication.
5. `model.json` stores cleaned keys. If a cleaner changes, models saved earlier
   stop matching exactly, and nothing warns about it.
6. A TD `Out` value is prefixed with `-` as text, without checking it. Dates are
   assumed to be ISO already and are not validated. Unparseable dates or
   amounts pass through as they are.
7. `-o` defaults to `model.json` in the current directory for `train`, not to
   `txmap/data/models/`.

---

## Code Style

This spec changes no code. Existing conventions are recorded here for anyone
writing a delta spec. Errors are one line on stderr that starts with `error:`
and names the fix:

```python
sys.exit(f"error: can't tell which bank {path} is from; pass --bank one of {sorted(BANKS)}")
```

Status messages go to stderr and data goes to stdout or `-o`. Ruff runs at line
length 120.

## Testing Strategy

- `tests/behaviour/` already asserts most of this contract through the CLI.
  [SPEC-01-behaviour-tests.md](./SPEC-01-behaviour-tests.md) lists what it covers.
  `--llm` through the CLI is deferred there because of the cache side effect.
  `tests/test_txmap.py` covers the internals: cleaner tables, the cascade, and
  `LLMNamer` with a fake client.
- This spec adds no tests. Verification is a review: each claim above can be
  traced to `txmap/cli.py`, `banks.py`, `model.py` or `llm.py` at `cccb5d5`.
  Where a behaviour test exists, it must agree.
- Contract items that no behaviour test covers yet (candidates for a later delta):
  the exact stderr status lines, `exact-other-bank`, majority vote on conflicting
  labels, the `eval` report format with `--folds`, exit code 2 for usage errors,
  all of the LLM step, and the edge-case behaviour list.

## Boundaries

- **Always:** keep this file in line with the code. When a delta spec ships,
  fold its outcome in here and bump the version (V2, …).
- **Ask first:** making any Python code public; dropping a promise, including
  an edge-case one; adding public surface (new flags, formats, env vars).
- **Never:** change code as part of this spec; describe planned behaviour as if
  it were current (planned items go in their own delta spec).

## Success Criteria

- [ ] Every subcommand, argument, default, output format, stderr message and
      exit code in `txmap/cli.py` appears in this spec, and nothing appears here
      that the code doesn't do.
- [ ] Every file format the tool reads or writes is described, including where
      it lives by default.
- [ ] What `--llm` sends off the machine, and what it writes to disk, is stated exactly.
- [ ] Nothing here contradicts a passing behaviour test. The two expected-failure
      tests in `tests/behaviour/test_map.py` are the only intentional divergence:
      they describe planned behaviour, and this spec describes current behaviour.
- [ ] No code changed. The only changes are under `spec/`, plus the updated
      links in `CLAUDE.md` and `tasks/`.

## Out of Scope (Deferred)

- **Changing any edge-case behaviour.** Each change is a behaviour change and
  needs a delta spec.
- **`map --model` required and no `--labels`.** This is already planned in
  `SPEC-01-behaviour-tests.md` and needs its own delta spec.
- **Other ideas in `.claude/prompts.md`:** `--version`, renaming `labels` to
  `merchants`, multiple `--model` values, an LLM-as-model design, and an
  option for the cache path.
- **A stable Python API.** Modules stay internal for now.
- **README and ARCHITECTURE cross-links to this file.** Adding them is a docs
  edit and can follow once this spec is approved.

## Decisions

1. **Location.** This spec is `spec/SPEC-00-interface.md`, the base spec. All
   specs live in `spec/`, and future `spec/SPEC-NN-<change>.md` deltas (numbered in order) point here.
2. **Python code is internal.** No module, function, constant or extension
   point is public, including how banks are added.
3. **Edge cases are promises.** Every item under
   [Edge-case behaviour](#edge-case-behaviour) is part of the contract.
4. **Confidence.** The cascade order and the confidence bands
   (1.0 / 0.95 / ≥0.7 / 0.5 / 0.0) are part of the contract. The exact
   similarity scores and the cleaning rules are tuning.

## Open Questions

None.
