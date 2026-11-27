# txmap Mission

Status: draft

This file states why `txmap` exists and where it is going. Every spec in this
folder should serve it. When a spec makes a trade-off, it should say which
principle below it follows. If a spec needs to break one, it should say so and
explain why.

## Mission

Turn any bank's messy transaction descriptions into the right merchant name, so
that the people building on top of it don't have to label transactions themselves.

Merchant mapping is the whole product. What a customer does with the names
afterwards, such as budgets, categories or reports, is up to them.

## Who it's for

- **Today:** the maintainer and early users, through the `txmap` CLI.
- **Future customer:** fintech and budgeting apps that need merchant enrichment
  in their own product. They will reach `txmap` through a **paid API service**.
  The CLI is the only interface for now.

## Where it's going

1. **CLI now.** Normalize exports, map descriptions, train and evaluate, all
   on the command line.
2. **Paid API later.** Send raw descriptors and get back merchant names with a
   confidence score.
3. **Global coverage eventually.** Start with Canadian banks (TD, Meridian) and
   grow to any bank in any locale.

The **core engine** (cleaning, model and prediction cascade) is the lasting
asset. The CLI and the future API are thin shells around it. Specs should put
their effort into the engine, and should not shape it around either shell.

## Principles

Listed in priority order. When two of them conflict, the one higher up wins.

1. **Low labelling effort.** The measure of success is how little a human has to
   review and label. Accuracy, coverage and the LLM step all serve this goal.
2. **Honest confidence.** A wrong answer with high confidence is the worst
   outcome. When the engine is unsure, the result must be flagged for review,
   never hidden. Confidence scores are part of the contract, and customers will
   rely on them.
3. **Local by default, LLM opt-in.** The core runs on the user's machine with no
   runtime dependencies and makes no network calls. The LLM step is an opt-in
   way to cut labelling. What it sends must be minimal and documented.
4. **A stable, tested public contract.** The public interface
   ([SPEC-00](./SPEC-00-interface.md)) is tested at the contract level
   ([SPEC-01](./SPEC-01-behaviour-tests.md)). Those tests do two jobs: they
   document the behaviour for maintainers, and they catch regressions so that
   internals can be refactored and improved safely. Contract changes are
   deliberate and come with a spec.
5. **Easy to add a bank.** Bank-specific code stays isolated, so adding a bank
   is cheap and doesn't affect the others.

## Success in about a year

- **Near-zero manual review.** In a typical month, new transactions map
  correctly without anyone touching the labels.
- **More banks supported.** Coverage goes well beyond the first two banks.
- **Others use it.** External users and contributors adopt it.
- **Stable, well-tested product.** The contract rarely breaks, and the
  behaviour tests catch it when it does.

## Non-goals

- **No categorisation.** No spending categories, budgets or reports.
- **No bank connections.** No Plaid, open banking or scraping. Input is exported
  files today, and API payloads later.
- **No storing customer data.** Don't keep customers' transactions beyond what
  the task needs. Labels and caches belong to whoever runs the tool.

Not ruled out yet: merchant metadata beyond the name, such as logos, locations
or MCC codes.

## Using this in specs

Each spec should answer these questions:

- Does it reduce labelling effort, or at least not increase it?
- Does it keep confidence honest?
- Does it keep the core local and dependency-free, with the LLM opt-in?
- Does it change the public contract? If so, link a delta spec and update the
  behaviour tests.
- Does it improve the engine, or does it only tune one shell?
