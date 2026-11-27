# Spec: Behaviour Tests — V1

Status: approved (rev 3: `cmd` runs through `uv`; everything lives under `tests/behaviour/`)

## Objective

Add tests that describe what `txmap` does from a user's point of view, so they:

1. **Guard against regressions.** If a change breaks something a user depends on (a file format, a merchant match, an error message that tells you what to do), a test fails.
2. **Serve as documentation you can run.** Reading the tests in pipeline order explains `normalize` → `train` → `map` → review → `eval`. In every test, the **act** step is a command you can copy into a shell and run from the repo root exactly as written:

   ```python
   cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json")
   ```

"Implementation-agnostic" means the tests only use the **public contract**: CLI arguments, input and output file formats, exit codes and messages. They don't know about cleaners, keys, trigrams, TF-IDF, cascade confidence values, or module and function names. You should be able to rewrite `banks.py` or `model.py`, swap the model, or rename modules, and these tests still pass.

The spec describes the **planned** contract for `map`: `--model` is required and there is no more training on the fly. That change isn't built yet, so the tests for it are written now and marked as expected failures until it lands (see Testing Strategy).

**Who it's for:** the maintainer (refactoring safely) and a new contributor (learning what the tool promises, by reading tests and pasting their commands).

## Tech Stack

- Python 3.13, standard-library `unittest`. No new dependencies.
- `cmd()` runs the given string as a separate process, exactly as written (`shlex.split`, no shell, no rewriting). Every command starts with `uv run txmap`, so what the test runs and what you paste are the same command. This needs `uv` on PATH, which it already is whenever the suite is run with `uv run`.

## Commands

```sh
uv run python -m unittest discover -s tests/behaviour -t . -v   # the behaviour spec, readable output
uv run python -m unittest                                       # whole suite (unit + behaviour)
uv run ruff check . && uv run ruff format --check               # lint

# Any act step, by hand, from the repo root, exactly as it appears in a test:
uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json
```

## Project Structure

Everything for this suite lives under `tests/behaviour/`. One test file per pipeline stage, plus test data laid out like `txmap/data/`:

```
tests/behaviour/__init__.py                → package docstring: what this suite is, the order to read the files in
tests/behaviour/helpers.py                 → cmd(), BehaviourTest base class, CSV read helpers (no txmap logic)
tests/behaviour/test_normalize.py          → 1. raw exports → standard CSV
tests/behaviour/test_train.py              → 2. labels → model file
tests/behaviour/test_map.py                → 3. standard CSV + model → labels draft
tests/behaviour/test_review.py             → 4. uncertain guesses → review CSV
tests/behaviour/test_eval.py               → 5. labels → unseen-descriptor accuracy
tests/behaviour/test_samples.py            → 6. the repo's shipped *.example.* files work end to end

tests/behaviour/data/raw/td.csv            → committed: TD export (no header) with every TD scenario row
tests/behaviour/data/raw/meridiancu.csv    → committed: Meridian export with every Meridian scenario row
tests/behaviour/data/raw/unknown-bank.csv  → committed: a CSV no bank recognises
tests/behaviour/data/out/labels.csv        → committed: the labels the model learns from
tests/behaviour/data/out/labels-eval.csv   → committed: labels with one row that can't be guessed when held out
tests/behaviour/data/normalized/           → generated (git-ignored)
tests/behaviour/data/models/               → generated (git-ignored)
tests/behaviour/data/out/* (other files)   → generated drafts and reviews (git-ignored)

.gitignore            → entries for the three generated paths above
tests/test_txmap.py   → unchanged (unit tests of internals, on purpose)
README.md             → one line under "Run the tests"
CLAUDE.md             → one short paragraph: what tests/behaviour/ is; keep it import-free
```

Raw fixtures are the single source of inputs. Map, review and train tests build their normalized input and model with `cmd(...)` in the arrange step, the same way a user would, so no hand-written normalized CSV can drift from what `normalize` actually produces.

## Code Style

Arrange, act and assert are visible in every test. Arrange and act are pasteable `cmd("uv run txmap ...")` lines, and assert reads output files or the command's result. Test names are sentences, with a docstring when the name alone doesn't explain the rule. Each file's module docstring says what that stage promises.

```python
# tests/behaviour/test_map.py
"""3. Map: `txmap map` names every normalized row using a trained model."""

from .helpers import BehaviourTest, cmd, merchants


class Map(BehaviourTest):
    def setUp(self):
        super().setUp()
        cmd(
            "uv run txmap normalize tests/behaviour/data/raw/td.csv tests/behaviour/data/raw/meridiancu.csv"
            " -o tests/behaviour/data/normalized/all.csv"
        )
        cmd("uv run txmap train tests/behaviour/data/out/labels.csv -o tests/behaviour/data/models/model.json")

    def test_same_merchant_is_recognised_across_banks(self):
        """Mobil is only labelled from TD, but a Meridian Mobil purchase still maps to it."""
        cmd(
            "uv run txmap map tests/behaviour/data/normalized/all.csv"
            " --model tests/behaviour/data/models/model.json -o tests/behaviour/data/out/draft.csv"
        )

        names = merchants("tests/behaviour/data/out/draft.csv")
        self.assertEqual(names["meridiancu", "POS Purchase Mobil 4361 Toronto Onca"], "Mobil")
```

(Each command stays on one line, even past 120 characters: E501 is not enabled and `ruff format` does not split strings, so it can be copied in one piece.)

- `cmd(line, fails=False)` runs from the repo root with `ANTHROPIC_*` removed from the environment. It returns `(returncode, stdout, stderr)` and asserts success, or failure when `fails=True`.
- Read helpers (`rows(path)`, `merchants(path)`, `review(path)`) only parse CSV. They contain no txmap logic.
- `BehaviourTest.setUp` deletes the generated paths, so a stale output from an earlier run can't make a test pass. Outputs are left in place after the run so you can inspect them.

## Testing Strategy

- **Level:** end-to-end through the CLI only. Unit-level detail, like the raw-descriptor → key tables, stays in `tests/test_txmap.py`.
- **Isolation:** each test starts from cleared generated paths and passes every input path explicitly, so results don't depend on this machine's `txmap/data/out/labels.csv`. No network.
- **Assert on contracts, not incidentals.** Assert exact columns and values. Assert that confidence is below the cutoff, not its exact number. Assert that error messages mention the remedy (`--bank`, `normalize`, `train`), not their exact wording. `uv` can print its own warnings to stderr, so never assert that stderr is empty.
- **Planned behaviour not built yet** is marked `@unittest.expectedFailure`, with a comment pointing to the planned change. The suite stays green. When the feature lands, those tests report "unexpected success", which is the signal to remove the decorator.
- **Runtime:** under 30 seconds for the behaviour suite on a laptop. `uv run` adds startup time to each process, and there are about 3 processes per test.

## Behaviours to cover

1. **Normalize** (`test_normalize.py`)
   - TD export → standard rows: money out negative, money in positive, ISO dates, description kept exactly.
   - Meridian export (header with stray spaces, timestamps, signed amounts) → standard rows.
   - Several exports, including mixed banks, → one header, then each file's rows in the order the files were given.
   - The bank is detected automatically, and `--bank <same bank>` gives the same output.
   - With no `-o`, output goes to stdout.
   - An unrecognised export → non-zero exit, and the message suggests `--bank`.
   - An unknown `--bank` value → non-zero exit, and the message lists the supported banks.
2. **Train** (`test_train.py`)
   - Training is deterministic: the same labels give an identical model file.
   - A trained model gives every labelled description its label.
3. **Map** (`test_map.py`)
   - A labelled description gets its label.
   - Noise such as store or branch numbers doesn't change the match.
   - The same merchant is recognised across banks.
   - Near-miss or truncated descriptions still match.
   - An unknown description gets a readable, non-empty name derived from the description.
   - The draft has one row per input row, in the same order, with descriptions exactly as given (duplicates kept).
   - The draft is a valid labels file: training on it and mapping again reproduces the same names, with nothing in review.
   - With no `-o`, output goes to stdout.
   - A raw bank export passed to `map` → non-zero exit, and the message points to `normalize`.
   - `map` never writes the private `txmap/data/out/labels.csv`.
   - **Planned (expected failure):** `map` without `--model` → non-zero exit, and the message points to `train`.
   - **Planned (expected failure):** `map --labels ...` is no longer accepted (no training on the fly).
4. **Review** (`test_review.py`)
   - Only uncertain guesses are listed, with columns `Bank,TransactionID,MerchantName,Confidence`.
   - Each description is listed once.
   - Uncertain guesses are flagged on stderr even without `--review`.
   - `--min-confidence` moves the cutoff: `1` sends everything except exact matches to review, and `0` sends nothing.
5. **Eval** (`test_eval.py`)
   - Reports an accuracy figure over every labelled row (`n/N`, where N is the number of label rows).
   - `-v` lists each miss with the expected and actual names. Without `-v`, misses aren't listed.
   - Output is identical on every run.
6. **Shipped samples** (`test_samples.py`; commands run on `txmap/data/*.example.*`, outputs go to `tests/behaviour/data/`)
   - Normalizing `meridiancu.example.csv` and `td.example.csv` reproduces `all.example.csv`.
   - `model.example.json` gives the same draft as a model freshly trained on `labels.example.csv`.
   - The README demo holds: TD `MOBIL@  - 4361    _F` and Meridian `POS Purchase Mobil 4361 Toronto Onca` both map to `Mobil`.

## Boundaries

- **Always:** make arrange and act steps pasteable `cmd("uv run txmap ...")` lines with repo-relative paths; write outputs only under the git-ignored `tests/behaviour/data/` paths; run ruff and the full suite before calling it done.
- **Ask first:** any production code change (including building the `--model`-required feature itself); adding a dependency; changing or deleting existing tests.
- **Never:** `import txmap` anywhere under `tests/behaviour/`; make network calls; write anywhere else in the repo, including `txmap/data/**` (the private `labels.csv` and `llm-cache.json`); commit.

## Success Criteria

- [ ] `tests/behaviour/` covers every bullet under "Behaviours to cover", and nothing under it imports `txmap`.
- [ ] Every arrange and act step is a single `cmd("uv run txmap ...")` string. Pasting a sample of them into a shell from the repo root works unchanged.
- [ ] `uv run python -m unittest` (whole suite) discovers and passes the behaviour tests, with only the planned tests showing as expected failures. `ruff check` and `ruff format --check` are clean. The behaviour suite runs in under 30 seconds.
- [ ] After a run, `git status` is clean and nothing under `txmap/data/` was created or modified.
- [ ] Mutation check: temporarily break each area (disable fuzzy matching, flip the TD amount sign, drop the `--bank` hint, break the review cutoff, make training order-dependent), confirm the matching tests fail, then revert each one. `git diff` on `txmap/` is empty at the end.
- [ ] `uv run python -m unittest discover -s tests/behaviour -t . -v` reads as a list of promises a non-author can follow.

## Out of Scope (Deferred)

- **All `--llm` behaviour through the CLI.** `map --llm` always saves `txmap/data/models/llm-cache.json` (even when no API call is made), and the CLI has no way to point that cache elsewhere. It's already covered by the `LLMFallback` unit tests. It comes back with the planned "LLM is just another model" change, or with a cache-path option.
- **Other planned changes in `.claude/prompts.md`:** renaming `normalized`, `--version`, `labels` → `merchants`, multiple models for `--model`, and the `model.py` rename. Their names and contracts aren't settled yet. Each will update these tests through its own delta.
- **Building the `--model`-required feature.** That's its own item. This spec only writes its tests (as expected failures).
- **Executable-markdown or doctest docs.** Named test files with docstrings and pasteable commands are enough.
- **Exact `eval` accuracy numbers and exact confidence values.** These are tuning outputs, not contract.

## Open Questions

None blocking. The defaults above stand unless you object:
- One test file per pipeline stage, read in the order listed in `tests/behaviour/__init__.py`.
- Planned-but-unbuilt tests use `@unittest.expectedFailure`.
- `--llm` tests are deferred because of the cache side effect.
