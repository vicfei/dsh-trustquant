# ahif × TrustQuant — dual audit chain demo

> 中文一句话：同一个基金，两条独立可验证的审计链——aihf 的哈希链决策账本（链 A：基金
> 做了什么决定、拿了什么仓）+ TrustQuant 的计算 manifest 链（链 B：这些仓位推出的数字
> 是否可复算）。两条链都不接受"自报数字"，都拒绝篡改。

This example demonstrates the concept-isomorphic pairing between two audit
disciplines, live on one fund:

| | chain A — decisions | chain B — calculations |
|---|---|---|
| owner | `aihf` (virattt/ai-hedge-fund) paper ledger | `trustquant` calculation manifests |
| unit | one hash-linked session record | one immutable manifest per run |
| guarantee | state only ever rebuilt by folding the chain; any edit/reorder/gap breaks replay | request + versions + digests recorded; replay re-executes and compares digests; the file's own `manifest_hash` fails integrity on any edit |
| tamper probe | bump one record's NAV on a copy → `LedgerError: … has been altered since it was written` | forge the claimed digest on a copy → `artifact_unavailable: manifest … failed integrity verification` |

## What actually runs

- The **real aihf 2.x engine**: mandate → `Fund` → per-session `tick` → paper
  broker → hash-chain ledger. The mandate is pead-only (a quant model), so no
  LLM, no API key. Market data is a **seeded synthetic market** (`synth.py`,
  seed 20260106) fed through aihf's own `DataClient` protocol — no network.
  Synthetic tickers are named `DEMO*` and labeled as such; the claim being
  demonstrated is about the chains, not the data.
- The **real trustquant runtime**: the fund's own marks CSV →
  `load_market_dataset` → `analyze_portfolio_risk` on the executed book's
  weights → manifest + `trustquant replay` (digest re-verified).

Determinism: two runs produce the identical ledger head hash and identical
risk numbers (`e508be55…` head, vol 0.26969… at aihf 2.7.0 × trustquant 0.2.0).

## Run

```bash
# prerequisites: aihf in a venv (pip install "aihf @ git+ssh://git@github.com/virattt/ai-hedge-fund.git"),
# trustquant on PATH or TRUSTQUANT_BIN set
~/.venvs/ahif/bin/python run_demo.py
# → out/dual_audit_report.{md,json}; exit 0 iff both chains verify and both tamper probes are REFUSED
```

Sample result (2026-11-06, aihf 2.7.0, trustquant 0.2.0):

```
sessions=74 records=74 decisions=74 executed=73
nav=97,389.02 positions={'DEMOB': 301, 'DEMOD': 1487}
chain A replay PASS head=e508be55… tamper_refused=True
chain B risk calc=… replay=PASS tamper_refused=True
```

The end-of-window book (DEMOB + DEMOD long, the two wave-2 8-K BEAT names)
is exactly what the pead model should hold given the synthetic earnings
calendar — the engine's behavior is internally consistent with its inputs.

## Going live (not part of the demo)

- Real market data: `aihf` ships `FDClient` (financialdatasets.ai, needs an
  API key); any `DataClient`-protocol implementation can be substituted the
  same way this demo substitutes one.
- LLM investor agents: aihf supports DeepSeek as a first-class provider
  (`ChatDeepSeek`, `DEEPSEEK_API_KEY`) — the demo deliberately stays
  quant-only for determinism.
