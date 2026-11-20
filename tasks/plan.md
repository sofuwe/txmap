# Plan: Behaviour Tests — V1

Implements [SPEC-behaviour-tests.md](../SPEC-behaviour-tests.md) (approved, rev 3). Tasks: [todo.md](./todo.md).

## Components and dependencies

```
helpers.py + fixtures + .gitignore ──┬──▶ test_normalize.py
                                     ├──▶ test_train.py
                                     ├──▶ test_map.py ──▶ test_review.py   (review reuses map's arrange step)
                                     ├──▶ test_eval.py
                                     └──▶ test_samples.py
all test files ──▶ docs (README, CLAUDE.md) ──▶ mutation check + final verification
```

- **Foundation (must be first):** `tests/behaviour/__init__.py`, `helpers.py`, the committed fixtures, and the `.gitignore` entries. Every test file depends on `cmd()`, the setUp cleanup, and the fixture rows.
- **Stage files are independent** of each other once the foundation exists. I'll build them in pipeline order anyway, because each one is a checkpoint and later files reuse arrange lines from earlier ones.
- **Docs and the mutation check come last.** They need the whole suite to exist.

## Fixture design (decided up front, so later tasks don't rewrite it)

All scenario rows live in two raw exports, and each row exists for a reason:

| File | Row (description) | Why it's there |
|---|---|---|
| `raw/td.csv` | `MOBIL@  - 4361    _F` (out 45.10) | exact label; README demo; money out → negative |
| | `DOLLARAMA #1348   _F` (out 8.47) | exact label |
| | `DOLLARAMA #9999   _F` (out 3.10) | store number differs from the label |
| | `SHOPPERS DRUG M   _F` (out 12.00) | exact label (added so every label appears in an export) |
| | `SHOPPERS DRUG MRT _F` (out 23.15) | near-miss: its fallback text would be "Shoppers Drug Mrt", so only fuzzy matching gives the label (was `...MART`, whose fallback text equals the label) |
| | `ZQXW HOLDINGS   _F` (out 9.99), twice | unknown → readable fallback and review; duplicates kept in the draft, listed once in review |
| | `MOBILE DEPOSIT` (in 500.00) | money in → positive |
| `raw/meridiancu.csv` (header with stray spaces) | `POS Purchase Mobil 4361 Toronto Onca` | same merchant from another bank; README demo |
| | `POS Purchase Bulk Barn 123 Toronto Onca` | exact label (added so every label appears in an export) |
| | `POS Purchase Bulk Barn 476 Mississ` | store number + cut-off city: cleans to the same text as the label, so a noise case, not a near-miss |
| | `POS Purchase Bulk Bar Toronto Onca` | near-miss: its fallback text would be "Bulk Bar" (added after the mutation check showed the original near-miss rows did not need fuzzy matching) |
| | `e-Transfer Out` | exact label |
| | `Payroll Deposit ACME` (+1200.50) | money in; unknown in Meridian |
| `raw/unknown-bank.csv` | `a,b` / `1,2` | no bank recognises it |
| `out/labels.csv` | 5 rows: Dollarama, Mobil (TD only), Shoppers Drug Mart, Bulk Barn (Meridian), Interac e-Transfer | small and readable; Mobil labelled from TD only, so the cross-bank match is real |
| `out/labels-eval.csv` | `labels.csv` + a second Dollarama branch + `ZQXW HOLDINGS   _F` → `Mystery Co` | 7 rows; "Mystery Co" can never be guessed when held out, so `-v` always has a miss to show |

Generated paths, which are git-ignored and cleared in `BehaviourTest.setUp`: `tests/behaviour/data/normalized/`, `tests/behaviour/data/models/`, and everything in `tests/behaviour/data/out/` except `labels*.csv`.

## Key implementation decisions

- **`cmd(line, fails=False)`:** `subprocess.run(shlex.split(line), cwd=REPO, env=<os.environ minus ANTHROPIC_*>, capture_output=True, text=True, check=False, timeout=120)`. It returns a small result with `returncode`, `stdout` and `stderr`. It's a module-level function, not a method, so test bodies read like shell sessions. It raises `AssertionError` with the command and stderr on an unexpected exit status, which unittest reports as a normal test failure.
- **Paths:** test bodies use repo-relative path strings, which is what you'd paste. Only `helpers.py` turns them into absolute paths, via `REPO`, for reading files.
- **The setUp cleanup** deletes only generated paths, worked out from the same rules as `.gitignore`, so it can never delete a committed fixture.
- **Arrange in setUp:** `test_map.py` and `test_review.py` run `normalize` and `train` in `setUp`, so each test body is just act and assert.
- **Expected failures:** two tests in `test_map.py`, each decorated with `@unittest.expectedFailure` and a `# Planned: --model required for map (.claude/prompts.md)` comment.
- **Private-labels guard:** compare the `mtime_ns` (or absence) of `txmap/data/out/labels.csv` before and after a `map` run. Read-only, so it works whether or not the file exists.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Nested `uv run` is slow or noisy | Measured: about 0.13 s per call with no extra stderr. About 120 calls ≈ 15 s, within the 30 s budget. Assertions never check that stderr is empty. |
| The expected-failure `map` without `--model` reads this machine's default labels | It only reads them, it doesn't write. The assertion is about the exit status and message, not the output, so the machine-specific default doesn't matter. |
| Fuzzy-match tests depend on tuning (`THRESHOLD`) | Already checked: `SHOPPERS DRUG MART _F` and `POS Purchase Bulk Barn 476 Mississ` match at the current settings. If tuning changes and they stop matching, that's a real behaviour change the suite should flag. |
| The cleanup deletes the wrong thing | It targets only the generated directories and `out/` files not named `labels*.csv`. Verified in task 1 by running twice and checking `git status`. |
| A mutation revert leaves the source changed | Mutate and revert with the Edit tool, one file at a time, then run `git diff --exit-code txmap/` at the end. |
| Something writes into `txmap/data/` | Before and after the full suite, take a listing of `txmap/data/` (paths and mtimes) and diff the two. No `--llm` tests are included (deferred). |

## Verification checkpoints

1. After the foundation and normalize: `test_normalize` passes, and `git status` is clean after running it twice.
2. After each stage file: that file passes on its own, and the whole suite still passes.
3. At the end: all success criteria in the spec, including the mutation check and the `txmap/data/` diff.
