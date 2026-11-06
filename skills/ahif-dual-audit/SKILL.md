---
name: ahif-dual-audit
description: Dual audit chains for an agentic fund — verify what the fund decided (aihf hash-chain ledger, chain A) and whether the numbers derived from that book recompute (TrustQuant manifests, chain B). Use when the person asks about agent-fund auditability, decision ledgers, tamper evidence, or wants the ahif x TrustQuant demo run and explained.
---

Use this skill when the person wants to see or explain **auditable agent
funds**: an agentic fund's *decisions* and the *numbers* those decisions rest
on can both carry "nothing self-reported, everything rebuildable" discipline.
This demo pairs the two systems that implement it:

- **Chain A — decisions**: `aihf` (virattt/ai-hedge-fund) paper ledger. Append-only,
  hash-linked session records; fund state is never stored, only rebuilt by
  folding the chain; any gap, reorder or edit breaks the chain and replay
  refuses. Kill switch (`control.json`) is part of the record.
- **Chain B — calculations**: TrustQuant manifests. Every run records request +
  engine/provider versions + input/result digests; the result itself is not
  stored — `trustquant replay` re-executes and compares digests; the manifest's
  own hash fails integrity verification on any edit.

They are concept-isomorphic on purpose: append-only record ↔ immutable
manifest; fold-to-rebuild ↔ re-execute-to-verify; chain break on edit ↔
digest/integrity mismatch on edit.

## Run the demo

```bash
cd /home/ubuntu/dsh-trustquant/examples/ahif-dual-audit
~/.venvs/ahif/bin/python run_demo.py        # ~1 min, offline, no keys
```

Requirements (checked by the script itself, fail-loud): aihf venv python,
`trustquant` on PATH (or `TRUSTQUANT_BIN`). Output:
`out/dual_audit_report.md` (+ `.json`). **Exit 0 iff** chain A replays, chain
B replays, and BOTH tamper probes are refused — treat any other exit as a
failed demo, never narrate around it.

The market is a seeded synthetic one (seed 20260106, `DEMO*` tickers, labeled
as such) fed through aihf's own `DataClient` protocol; the mandate is
pead-only (quant model: no LLM, no key). Two runs reproduce the identical
ledger head hash and risk numbers — say so when asked about reproducibility.

## What to verify and report (in this order)

1. **Chain A**: record count, head hash, replay PASS, final NAV and positions
   from the folded state. Tamper probe result — mutating one record's NAV must
   produce a `LedgerError`, quote it.
2. **Chain B**: the dataset is the fund's own marks CSV; report the
   `calculation_id` for `analyze_portfolio_risk` on the executed book's
   weights, its risk numbers **with their conventions** (daily simple returns,
   252-day annualization, daily fixed-weight rebalancing), and `trustquant
   replay` PASS. Tamper probe result — forging the manifest's claimed digest
   must produce `artifact_unavailable … failed integrity verification`, quote it.
3. **The isomorphism table** (both READMEs carry it) — explain WHY the pairing
   matters: chain A answers *what the fund decided and holds*, chain B answers
   *whether the numbers derived from that book recompute exactly*; neither
   chain trusts the other.

## Discipline rules

- Never present synthetic-market numbers as market data; the demo's claim is
  about the audit chains, and every artifact labels the data as synthetic.
- Weights for `analyze_portfolio_risk` must cover every ticker in the dataset
  (flat names carry 0.0) — a missing ticker is `invalid_input`, fix and rerun.
- Replay PASS means "same version, same environment reproduces the number" —
  never promise cross-version reproducibility.
- Going live: real data needs an aihf data credential (financialdatasets.ai);
  LLM investor agents support DeepSeek (`DEEPSEEK_API_KEY`). The demo stays
  quant-only for determinism — say this when asked, don't improvise a live run.
