# Tasks: Behaviour Tests — V1

Spec: [SPEC-behaviour-tests.md](../SPEC-behaviour-tests.md) · Plan: [plan.md](./plan.md)

Shorthand: `BT` = `uv run python -m unittest discover -s tests/behaviour -t . -v`

- [x] **1. Foundation + Normalize**
  - Acceptance: the `tests/behaviour/` package exists, with the `__init__.py` docstring (purpose, reading order) and `helpers.py` (`cmd`, `BehaviourTest` with the generated-path cleanup, `rows`/`merchants`/`review` readers). The fixtures from the plan's table are committed. The `.gitignore` entries are added. `test_normalize.py` covers all 7 Normalize bullets.
  - Verify: `BT` passes. Run it twice, then `git status` shows only the new committed files (no generated outputs). `grep -rn "import txmap\|from txmap" tests/behaviour` returns nothing.
  - Files: `tests/behaviour/__init__.py`, `tests/behaviour/helpers.py`, `tests/behaviour/test_normalize.py`, `tests/behaviour/data/raw/{td,meridiancu,unknown-bank}.csv`, `tests/behaviour/data/out/labels.csv`, `.gitignore`

- [x] **2. Train**
  - Acceptance: `test_train.py` covers both Train bullets (deterministic model file; every label is recovered by `map --model`).
  - Verify: `BT` passes.
  - Files: `tests/behaviour/test_train.py`

- [x] **3. Map**
  - Acceptance: `test_map.py` covers all 12 Map bullets. The 2 planned ones are `@unittest.expectedFailure` with a pointer comment. `setUp` arranges normalize + train with `cmd(...)`.
  - Verify: `BT` passes with exactly 2 expected failures. `txmap/data/out/labels.csv` is unchanged (it's guarded by the test itself).
  - Files: `tests/behaviour/test_map.py`

- [x] **4. Review**
  - Acceptance: `test_review.py` covers all 4 Review bullets.
  - Verify: `BT` passes.
  - Files: `tests/behaviour/test_review.py`

- [x] **5. Eval**
  - Acceptance: `labels-eval.csv` is committed. `test_eval.py` covers all 3 Eval bullets.
  - Verify: `BT` passes.
  - Files: `tests/behaviour/data/out/labels-eval.csv`, `tests/behaviour/test_eval.py`

- [x] **6. Shipped samples**
  - Acceptance: `test_samples.py` covers all 3 Samples bullets. Commands read `txmap/data/*.example.*`, and outputs go only to `tests/behaviour/data/`.
  - Verify: `BT` passes.
  - Files: `tests/behaviour/test_samples.py`

- [x] **7. Docs**
  - Acceptance: one line in the README's "Run the tests" block (the `BT` command). One paragraph in CLAUDE.md: what `tests/behaviour/` is, that it must stay free of `txmap` imports, and to update it together with README when the contract changes on purpose.
  - Verify: read both diffs.
  - Files: `README.md`, `CLAUDE.md`

- [x] **8. Mutation check + final verification**
  - Acceptance: each of these mutations, applied alone, makes at least one test in the matching file fail, and is then reverted:
    1. disable fuzzy matching (`THRESHOLD` out of reach) → `test_map`
    2. flip the TD money-out sign → `test_normalize`
    3. drop the `--bank` hint from the undetectable-export error → `test_normalize`
    4. invert the review cutoff comparison → `test_review`
    5. make training depend on label order (e.g. shuffle entries) → `test_train`
  - Verify:
    - `git diff --exit-code txmap/` is clean.
    - The full `uv run python -m unittest` passes (2 expected failures).
    - `uv run ruff check . && uv run ruff format --check` is clean.
    - `BT` takes under 30 s.
    - A `txmap/data/` listing (paths and mtimes) before and after the run is identical.
    - `git status` shows only the intended files.
    - Pasting 3 sample `cmd(...)` strings into a shell from the repo root works.
  - Files: none changed at the end (mutations are temporary)
