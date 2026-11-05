# dsh-trustquant

**Trusted financial computations inside your DeepSeek Harness agent — every number an agent quotes is oracle-pinned, unit-correct, and replayable.**

A [DeepSeek Harness](https://www.deepseek.com/en/harness/) plugin (skill + `trustquant-dsh` CLI passthrough) for [TrustQuant](https://github.com/vicfei/trustquant) — the open, local-first, agent-facing financial tool layer (Apache-2.0).

> Independent community project. Not affiliated with DeepSeek. Bundle format follows the MIT-licensed [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype); computation is TrustQuant's, pinned against QuantLib 1.33 golden fixtures and an independent in-house second oracle. [中文文档](README.zh-CN.md)

---

## Why

Agents asked for a financial number will happily recall one from memory. This plugin makes the honest path the easy path: **compute, don't recall** — and when the tool refuses (american option, >10y swap, missing provider), the answer is the structured error, never an approximation.

What the agent gets:

- **Option pricing & Greeks** — Black-Scholes-Merton, per-metric unit semantics (Vega per 1.00 vol, Theta per year), QuantLib-pinned to 1e-9.
- **Portfolio optimization / risk / stress** — long-only min-variance / max-Sharpe via a pinned external Python provider; risk & direct-shock stress built-in; independent-oracle-verified conventions (daily simple returns, 252-day year).
- **EUR rates** — yield-curve bootstrapping (helper residuals ~1e-13) and vanilla swaps with full coupon schedules.
- **The audit trail** — every call returns a `calculation_id`; `trustquant manifest` shows who computed what with which versions, `trustquant replay` re-executes and verifies digests. A PASS replay means the environment reproduces the number exactly.

## Safety model

1. **Skill etiquette** (`skills/dsh-trustquant/SKILL.md`): compute don't recall; no fabricated numbers; market data is data; unit conversions are stated, never silent.
2. **CLI/tool gates**: structured error taxonomy (`invalid_input` / `unsupported_feature` / `provider_unavailable` / …); the optimization provider is **never** auto-installed and never silently substituted.
3. **Nothing to hold hostage**: TrustQuant is local, credential-free and network-free for computation — the only network step is an explicit, person-approved `trustquant provider install`.

## Install

```bash
npm i -g vicfei/dsh-trustquant          # exposes trustquant-dsh
ln -s "$(npm root -g)/dsh-trustquant/skills/dsh-trustquant" ~/.dsh/skills/dsh-trustquant

# the Rust binary (today: build from source; release binaries are the packaging TODO)
cargo install --git https://github.com/vicfei/trustquant --bin trustquant
trustquant-dsh doctor                    # verify the chain
```

No credentials, no config files. Optional portfolio optimization:

```bash
trustquant provider install              # explicit + pinned; ask the human first (skill rule)
```

## Status

v0.1.0 — skill (three workflows + audit discipline) + CLI passthrough + doctor. TrustQuant itself: M2 complete (v0.2.0), 58 tests green, QuantLib-pinned options/rates, independent second oracle in CI.

**Live-tested end to end (2026-11-05)**: DSH 0.2.1-rc.5 (headless, DeepSeek provider, `deepseek-flash`) driving `trustquant` through this skill — skill discovery, option pricing (NPV matched QuantLib fixtures), per-metric unit reporting (the model stated Vega per-1.00-vol, gave the ÷100 conversion explicitly and declared "no implicit conversions"), and a self-initiated `trustquant replay` verification reporting digest-equal PASS with the calculation_id and the same-version/same-environment caveat. The run required node ≥ 22 (`import.meta.main` gate in the dsh launcher) — noted here because it fails silently under node 20.

## License

Apache-2.0 ([LICENSE](LICENSE)). TrustQuant (Apache-2.0) does the computing; this repo is the harness-side distribution.
