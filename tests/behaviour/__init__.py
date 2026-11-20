"""Behaviour spec for txmap: what a user can rely on, independent of how it's built.

These tests drive the real CLI and only look at what a user sees: the files it
writes, its exit status and its messages. Nothing here imports txmap, so you
can rewrite cleaners, swap the model or rename modules and they should still
pass. If one fails, either a change broke something users depend on, or the
contract changed on purpose and the test (and README) should change with it.

Every arrange and act step is a `cmd("uv run txmap ...")` line. Paste it into a
shell from the repo root to run that step yourself.

Read the files in pipeline order:

  1. test_normalize.py  raw bank exports            -> standard CSV
  2. test_train.py      labels                      -> model file
  3. test_map.py        standard CSV + model        -> labels draft
  4. test_review.py     uncertain guesses           -> review CSV
  5. test_eval.py       labels                      -> accuracy on unseen descriptions
  6. test_samples.py    the repo's *.example.* files work end to end

Inputs live in tests/behaviour/data/ (committed); outputs land next to them
(git-ignored, cleared before each test).

Run:  uv run python -m unittest discover -s tests/behaviour -t . -v
"""
