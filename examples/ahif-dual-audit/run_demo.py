#!/usr/bin/env python3
"""ahif x TrustQuant dual-audit-chain demo.

Run (needs the aihf venv python and the trustquant binary on PATH or
TRUSTQUANT_BIN):

    ~/.venvs/ahif/bin/python run_demo.py [--out DIR]

What it demonstrates
--------------------
Two independent, independently-verifiable audit chains over ONE fund:

  Chain A — decisions: the aihf paper ledger (hedge_fund/paper/ledger.py),
  an append-only hash-linked book of session records. The fund's state is
  never stored, only rebuilt by folding the chain; any gap, reorder or edit
  breaks it and replay refuses.

  Chain B — calculations: TrustQuant manifests. Every trustquant run records
  the request, engine/provider versions, and an input + result digest; the
  result itself is not stored — `trustquant replay` re-executes and compares
  digests.

The demo runs the REAL aihf engine over a seeded synthetic market (synth.py
— no network, no API key, no LLM; the mandate is pead-only, a quant model),
then:
  1. verifies chain A by replaying the whole ledger,
  2. loads the fund's own marks into trustquant and audits the executed
     book's portfolio risk (chain B), then replays that calculation,
  3. proves both chains refuse tampering: mutate a ledger record's NAV on a
     copy -> chain A replay refuses; mutate the manifest's claimed result
     digest on a copy -> replay reports digest mismatch,
  4. writes dual_audit_report.{md,json}.

Exit 0 iff every chain verifies and both tamper probes are REFUSED.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from synth import BENCHMARK, UNIVERSE, SyntheticDataClient, SyntheticMarket  # noqa: E402

NEW_YORK = ZoneInfo("America/New_York")
FUND_NAME = "dual-audit-demo"
TRUSTQUANT_BIN = os.environ.get("TRUSTQUANT_BIN", "trustquant")

_req_counter = 0


def tq_run(request: dict, data_dir: Path) -> dict:
    global _req_counter
    _req_counter += 1
    req = data_dir.parent / f".req_{os.getpid()}_{_req_counter}.json"
    req.write_text(json.dumps(request))
    proc = subprocess.run(
        [TRUSTQUANT_BIN, "run", str(req)],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "TRUSTQUANT_DATA_DIR": str(data_dir)},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"trustquant run failed: {proc.stderr.strip()[:400]}")
    out = json.loads(proc.stdout)
    if out.get("status") != "success":
        raise RuntimeError(f"trustquant non-success: {json.dumps(out)[:400]}")
    return out


def tq_replay(calculation_id: str, data_dir: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [TRUSTQUANT_BIN, "replay", calculation_id, "--json"],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "TRUSTQUANT_DATA_DIR": str(data_dir)},
    )
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, (proc.stdout + proc.stderr).strip()[:400]
    if parsed.get("status") == "error":
        err = parsed.get("error", {})
        return False, f"{err.get('error_type')}: {err.get('message', '')[:200]}"
    ok = proc.returncode == 0 and parsed.get("result_digest_match") is True
    return ok, json.dumps({k: parsed[k] for k in
                           ("result_digest_match", "manifest_hash_valid")
                           if k in parsed})[:400]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(HERE / "out"), help="output directory")
    args = parser.parse_args()

    from hedge_fund.fund import load_spec
    from hedge_fund.paper.deployed import deploy
    from hedge_fund.paper.ledger import Ledger
    from hedge_fund.paper.tick import tick
    from hedge_fund.pipeline.session import FundHalted

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    tqdata = out / "tqdata"
    tqdata.mkdir(parents=True)
    ran_at = datetime.now().astimezone().isoformat(timespec="seconds")

    market = SyntheticMarket()
    client = SyntheticDataClient(market)
    n_rows = market.closes_csv(out / "marks.csv")

    # ---- chain A: run the real aihf engine over the synthetic market ------
    spec = load_spec(HERE / "mandate.yaml")
    fund_dir = deploy(FUND_NAME, spec, UNIVERSE, root=out)
    n_decisions = n_executed = 0
    halted: str | None = None
    for session_day in market.dates:
        # one tick per session; the injected clock is the evening after the
        # session, so the session is exactly what the fund owes next
        moment = (datetime.combine(session_day + timedelta(days=1), datetime.min.time(),
                                   tzinfo=NEW_YORK)).replace(hour=18)
        try:
            record = tick(fund_dir, client, now=lambda: moment)
            n_decisions += record.decision is not None
            n_executed += record.executed is not None
        except FundHalted as exc:
            halted = str(exc)
            break
    if halted:
        raise RuntimeError(f"fund halted mid-demo: {halted}")

    ledger = Ledger(fund_dir)
    sessions = ledger.sessions()
    state = ledger.replay(spec.capital)          # verifies the whole chain
    head_hash = state.prev_hash
    n_records = len(sessions)

    last_day = market.dates[-1].isoformat()
    last_close = {t: market.bars[t][last_day].close for t in UNIVERSE}
    invested = {t: qty * last_close[t] for t, qty in state.positions.items() if qty}
    total_invested = sum(invested.values())
    if total_invested <= 0:
        raise RuntimeError("fund is flat at the last session — no book to audit")
    # the risk tool requires a weight for every ticker in the dataset;
    # flat names carry 0.0
    weights = {t: round(invested.get(t, 0.0) / total_invested, 10) for t in UNIVERSE}
    nav = state.cash + total_invested

    # ---- chain A tamper probe: bump one record's NAV on a COPY ------------
    tamper_dir = out / "tamper-A"
    shutil.copytree(fund_dir, tamper_dir)
    records = sorted((tamper_dir / "ledger").glob("*.json"))
    victim = records[len(records) // 2]
    doc = json.loads(victim.read_text())
    if isinstance(doc.get("nav"), (int, float)):
        doc["nav"] = round(doc["nav"] * 1.01, 4)
    else:
        doc["session"] = "1999-01-01"            # any edit must break the chain
    victim.write_text(json.dumps(doc))
    try:
        Ledger(tamper_dir).replay(spec.capital)
        tamper_a = {"refused": False, "note": "MUTATION ACCEPTED — chain broken!"}
    except Exception as exc:
        tamper_a = {"refused": True, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}

    # ---- chain B: audit the executed book's risk with trustquant ----------
    ds = tq_run({"schema_version": "0.2", "tool": "load_market_dataset",
                 "params": {"path": str(out / "marks.csv")}}, tqdata)
    dataset_id = ds["result"]["dataset_id"]
    risk = tq_run({"schema_version": "0.2", "tool": "analyze_portfolio_risk",
                   "params": {"dataset": dataset_id, "weights": weights}}, tqdata)
    risk_result = risk["result"]
    risk_calc = risk["calculation_id"]
    replay_ok, replay_out = tq_replay(risk_calc, tqdata)

    # ---- chain B tamper probe: forge the manifest's claimed digest ---------
    tamper_tq = out / "tamper-B"
    shutil.copytree(tqdata, tamper_tq)
    stored = tamper_tq / "calculations" / f"{risk_calc}.json"
    doc = json.loads(stored.read_text())
    digest = doc["result_digest"]
    doc["result_digest"] = digest[:-1] + ("0" if digest[-1] != "0" else "1")
    stored.write_text(json.dumps(doc))
    tamper_ok, tamper_out = tq_replay(risk_calc, tamper_tq)
    tamper_b = {"refused": not tamper_ok,
                "note": ("claimed digest still matched — chain broken!" if tamper_ok
                         else tamper_out)}

    # ---- verdict + report --------------------------------------------------
    verdict = ("dual-audit PASS" if (tamper_a["refused"] and tamper_b["refused"] and replay_ok)
               else "DUAL-AUDIT FAIL")

    report = {
        "kind": "ahif x TrustQuant dual-audit demo",
        "ran_at": ran_at,
        "versions": {
            "aihf": importlib.metadata.version("aihf"),
            "trustquant": subprocess.run([TRUSTQUANT_BIN, "version"], capture_output=True,
                                         text=True, timeout=30).stdout.strip(),
            "python": sys.version.split()[0],
        },
        "data": {"market": "seeded synthetic (seed 20260106), labeled as such",
                 "sessions": len(market.dates), "universe": UNIVERSE,
                 "benchmark": BENCHMARK, "marks_csv_rows": n_rows},
        "chain_a": {
            "what": "aihf paper ledger — append-only hash-linked session records; state only ever rebuilt by folding the chain",
            "fund": FUND_NAME, "records": n_records, "head_hash": head_hash,
            "replay": "PASS (whole chain folded; state rebuilt from records)",
            "decisions": n_decisions, "executed": n_executed,
            "final_nav": nav, "cash": state.cash,
            "positions": {t: int(q) for t, q in state.positions.items() if q},
            "tamper_probe": tamper_a,
        },
        "chain_b": {
            "what": "TrustQuant calculation manifests — request+versions+digests recorded per run; the result is re-executed by replay, never stored",
            "dataset_id": dataset_id, "dataset_source": "the fund's own marks (marks.csv)",
            "calculation_id": risk_calc, "manifest_hash": risk.get("manifest_hash"),
            "risk": {k: risk_result[k] for k in risk_result if k != "units"},
            "units": risk_result.get("units"),
            "replay": "PASS" if replay_ok else "FAIL",
            "tamper_probe": tamper_b,
        },
        "isomorphism": [
            ["append-only record per session", "immutable manifest per calculation"],
            ["each record carries the previous record's hash", "each manifest carries input + result digests"],
            ["state is rebuilt by folding, never stored", "the number is re-executed by replay, never trusted"],
            ["an edited record breaks the chain and replay refuses", "a forged digest fails the recomputation and replay reports mismatch"],
            ["kill switch (control.json) halts trading, on-chain", "provider/engine versions pinned in the manifest, on-record"],
        ],
        "verdict": verdict,
    }
    (out / "dual_audit_report.json").write_text(json.dumps(report, indent=1))

    lines = [
        "# ahif × TrustQuant — dual audit chain demo",
        "",
        f"Ran {ran_at} · verdict: **{verdict}**",
        "",
        "One fund, two independent audit chains. Market data: "
        f"{report['data']['market']}; universe {', '.join(UNIVERSE)} vs benchmark "
        f"{BENCHMARK}. The aihf engine, its paper broker and its hash-chain ledger are",
        "the real `aihf` 2.x code paths; the numbers are audited by the real `trustquant` runtime.",
        "",
        "## Chain A — decisions (aihf paper ledger)",
        "",
        f"- {n_records} session records, head hash `{head_hash}`",
        f"- replay: {report['chain_a']['replay']}",
        f"- decisions {n_decisions} · executed {n_executed} · final NAV {nav:,.2f} "
        f"(cash {state.cash:,.2f} + invested {total_invested:,.2f})",
        f"- positions at last session ({last_day}): "
        + (", ".join(f"{t} {q}× @ {last_close[t]}" for t, q in sorted(state.positions.items()) if q)
           or "flat"),
        f"- tamper probe: {'REFUSED' if tamper_a['refused'] else 'ACCEPTED'} — {tamper_a['note']}",
        "",
        "## Chain B — calculations (TrustQuant manifests)",
        "",
        f"- dataset `{dataset_id}` = the fund's own marks CSV ({n_rows} rows)",
        f"- `analyze_portfolio_risk` on the executed book's weights → calculation `{risk_calc}`",
        f"- replay: {'PASS' if replay_ok else 'FAIL'} · tamper probe: "
        f"{'REFUSED' if tamper_b['refused'] else 'ACCEPTED'} — {tamper_b['note']}",
        "",
        "## The isomorphism (why this pairing matters)",
        "",
        "| chain A: aihf ledger | chain B: TrustQuant manifest |",
        "|---|---|",
        *[f"| {a} | {b} |" for a, b in report["isomorphism"]],
        "",
        "An agentic fund's decisions and the numbers those decisions rest on can carry",
        "the same discipline: nothing self-reported, everything rebuildable from a record",
        "that refuses edits. Chain A answers *what the fund decided and holds*; chain B",
        "answers *whether the numbers derived from that book recompute exactly*. Neither",
        "chain trusts the other — and both refuse tampering.",
        "",
    ]
    (out / "dual_audit_report.md").write_text("\n".join(lines))

    print(f"sessions={len(market.dates)} records={n_records} decisions={n_decisions} executed={n_executed}")
    print(f"nav={nav:,.2f} positions={ {t: q for t, q in state.positions.items() if q} }")
    print(f"chain A replay PASS head={head_hash} tamper_refused={tamper_a['refused']}")
    print(f"chain B risk calc={risk_calc} replay={'PASS' if replay_ok else 'FAIL'} tamper_refused={tamper_b['refused']}")
    print(f"report: {out / 'dual_audit_report.md'}")
    return 0 if verdict == "dual-audit PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
