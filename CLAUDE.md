# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`txmap` maps messy bank transaction descriptions (e.g. `MOBIL@  - 4361    _F`) to clean merchant names using a small nearest-neighbour model trained on labelled examples. README.md has the full user-facing docs, pipeline diagram and the prediction cascade; read it before changing behaviour.

## Commands

See [README.md](./README.md)

## Architecture

Pipeline: raw bank export → `normalize` → standard CSV (`Bank,TransactionID,Date,Amount`) → `map` → labels draft (`Bank,TransactionID,MerchantName`). `TransactionID` is the raw bank description, not an ID.

- `txmap/banks.py` — the only bank-specific code. `BANKS` registers a `(parser, cleaner)` per bank; `detect()` sniffs the export format. A *cleaner* reduces a raw descriptor to a stable uppercase *key* (strips store numbers, dates, amounts, prefixes, city suffixes). Cleaning quality drives everything downstream; the `CleanTD`/`CleanMeridian` tests are a table of raw → key cases — extend them when changing a cleaner.
- `txmap/model.py` — `Model.predict()` returns `(merchant, confidence, source)` via a cascade: exact key+bank (1.0) → exact key any bank (0.95) → char-trigram TF-IDF cosine ≥ `THRESHOLD` with `SAME_BANK_BONUS` (capped at 0.99) → optional LLM namer (`LLM_CONFIDENCE` 0.5, deliberately below the 0.7 review threshold so LLM guesses always land in review) → title-cased key (0.0). The model is trained from labels on the fly unless `--model` points at a saved `model.json`.
- `txmap/llm.py` — `LLMNamer`, the optional Claude step. Lazily imports `anthropic` so the core stays dependency-free. Uses structured JSON output at low effort, plus the server-side fallback beta for models in `_FALLBACK_MODELS`. Answers are cached in `txmap/data/models/llm-cache.json` keyed by `PROMPT_VERSION|model|bank|raw` — **bump `PROMPT_VERSION` whenever the prompt or `SYSTEM` changes.** A refusal/non-`end_turn` returns `None` so the cascade falls through. Missing/rejected API keys become a `SystemExit` with a friendly message.
- `txmap/cli.py` — argparse subcommands (`normalize`, `map`, `train`, `eval`); runs LLM calls concurrently (8 threads), which is why `LLMNamer` guards its cache with a lock.

`tests/behaviour/` is a black-box spec of the CLI contract, written up in `SPEC-behaviour-tests.md`. Every arrange and act step is a pasteable `cmd("uv run txmap ...")` line, inputs are committed under `tests/behaviour/data/`, and outputs there are git-ignored. Nothing under `tests/behaviour/` may import `txmap`. If one of these tests fails after a refactor, a user-facing behaviour broke. If the contract changed on purpose, update the test together with README.md.

Tests never hit the network: `LLMNamer` accepts an injected `client` (see `_FakeClient` in `tests/test_txmap.py`, which mimics `client.beta.messages.create`) and a temp `cache_path`.

For more details, see [ARCHITECTURE.md](./ARCHITECTURE.md)

## Data and privacy

`txmap/data/{raw,normalized,out,models}/` are git-ignored except `*.example.*` files. Real labels live in `txmap/data/out/labels.csv`; the CLI uses it by default when it exists, otherwise `labels.example.csv` — so `eval` numbers differ between machines. The tool never writes `labels.csv` itself. Don't commit real transaction data; add samples only as `*.example.csv`.

## Adding a bank

In `banks.py`: write a parser and cleaner, register them in `BANKS`, teach `detect()` the export shape. Then add `txmap/data/raw/<bank>.example.csv` and a few rows to `txmap/data/out/labels.example.csv`.
